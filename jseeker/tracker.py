"""jSeeker Tracker — SQLite CRUD for applications with 3 status pipelines."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from jseeker.models import (
    APICost,
    Application,
    Company,
    DiscoveryStatus,
    JobDiscovery,
    Resume,
    SearchTag,
)


def _get_db_path() -> Path:
    from config import settings
    return settings.db_path


def _normalize_discovery_status(status: str | DiscoveryStatus | None) -> str:
    """Normalize discovery status values for consistent filtering."""
    allowed = {s.value for s in DiscoveryStatus}
    if isinstance(status, DiscoveryStatus):
        normalized = status.value
    else:
        normalized = str(status or DiscoveryStatus.NEW.value).strip().lower()
    return normalized if normalized in allowed else DiscoveryStatus.NEW.value


def _normalize_search_tag(tag: str) -> str:
    """Normalize a search tag by trimming and collapsing whitespace."""
    return " ".join((tag or "").strip().split())


def init_db(db_path: Path = None) -> None:
    """Initialize the SQLite database with all tables."""
    if db_path is None:
        db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        industry TEXT,
        size TEXT,
        detected_ats TEXT,
        careers_url TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY,
        company_id INTEGER REFERENCES companies(id),
        role_title TEXT NOT NULL,
        jd_text TEXT,
        jd_url TEXT,
        salary_range TEXT,
        location TEXT,
        remote_policy TEXT,
        relevance_score REAL,
        resume_status TEXT DEFAULT 'draft',
        application_status TEXT DEFAULT 'not_applied',
        job_status TEXT DEFAULT 'active',
        job_status_checked_at TIMESTAMP,
        applied_date DATE,
        last_activity DATE,
        recruiter_name TEXT,
        recruiter_email TEXT,
        recruiter_linkedin TEXT,
        outreach_sent BOOLEAN DEFAULT FALSE,
        outreach_text TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS resumes (
        id INTEGER PRIMARY KEY,
        application_id INTEGER REFERENCES applications(id),
        version INTEGER DEFAULT 1,
        template_used TEXT,
        content_json TEXT,
        pdf_path TEXT,
        docx_path TEXT,
        ats_score INTEGER,
        ats_platform TEXT,
        generation_cost REAL,
        user_edited BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS api_costs (
        id INTEGER PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        model TEXT,
        task TEXT,
        input_tokens INTEGER,
        output_tokens INTEGER,
        cache_tokens INTEGER,
        cost_usd REAL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS job_discoveries (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        company TEXT,
        location TEXT,
        salary_range TEXT,
        url TEXT UNIQUE,
        source TEXT,
        posting_date DATE,
        search_tags TEXT,
        status TEXT DEFAULT 'new',
        imported_application_id INTEGER REFERENCES applications(id),
        discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS search_tags (
        id INTEGER PRIMARY KEY,
        tag TEXT NOT NULL UNIQUE,
        active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS feedback_events (
        id INTEGER PRIMARY KEY,
        resume_id INTEGER REFERENCES resumes(id),
        event_type TEXT,
        field TEXT,
        original_value TEXT,
        new_value TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS learned_patterns (
        id INTEGER PRIMARY KEY,
        pattern_type TEXT NOT NULL,
        source_text TEXT NOT NULL,
        target_text TEXT NOT NULL,
        jd_context TEXT,
        frequency INTEGER DEFAULT 1,
        confidence REAL DEFAULT 1.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(pattern_type, source_text, jd_context)
    )""")

    c.execute("CREATE INDEX IF NOT EXISTS idx_pattern_type ON learned_patterns(pattern_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_frequency ON learned_patterns(frequency DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_last_used ON learned_patterns(last_used_at DESC)")

    c.execute("""CREATE TABLE IF NOT EXISTS jd_cache (
        id INTEGER PRIMARY KEY,
        pruned_text_hash TEXT UNIQUE NOT NULL,
        parsed_json TEXT NOT NULL,
        title TEXT,
        company TEXT,
        ats_keywords TEXT,
        hit_count INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("CREATE INDEX IF NOT EXISTS idx_jd_cache_title ON jd_cache(title)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_jd_cache_hits ON jd_cache(hit_count DESC)")

    c.execute("""CREATE TABLE IF NOT EXISTS search_sessions (
        id INTEGER PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active',
        tags TEXT,
        markets TEXT,
        sources TEXT,
        limit_reached BOOLEAN DEFAULT FALSE,
        total_found INTEGER DEFAULT 0,
        completed_at TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS tag_weights (
        tag TEXT PRIMARY KEY,
        weight INTEGER DEFAULT 50,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS batch_jobs (
        id TEXT PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        status TEXT DEFAULT 'running',
        total_count INTEGER DEFAULT 0,
        completed_count INTEGER DEFAULT 0,
        failed_count INTEGER DEFAULT 0,
        skipped_count INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS batch_job_items (
        id INTEGER PRIMARY KEY,
        batch_id TEXT REFERENCES batch_jobs(id),
        url TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        error TEXT,
        resume_id INTEGER REFERENCES resumes(id),
        application_id INTEGER REFERENCES applications(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP
    )""")

    c.execute("CREATE INDEX IF NOT EXISTS idx_batch_job_items_batch_id ON batch_job_items(batch_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_batch_job_items_status ON batch_job_items(status)")

    c.execute("""CREATE TABLE IF NOT EXISTS saved_searches (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        tag_weights TEXT NOT NULL,
        markets TEXT,
        sources TEXT,
        location TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.commit()
    conn.close()

    # Run migrations after initial schema creation
    _run_migrations(db_path)


def _run_migrations(db_path: Path) -> None:
    """Run all pending database migrations."""
    try:
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()

        # Check if market column exists in job_discoveries
        c.execute("PRAGMA table_info(job_discoveries)")
        columns = [row[1] for row in c.fetchall()]

        if "market" not in columns:
            try:
                c.execute("ALTER TABLE job_discoveries ADD COLUMN market TEXT")
                conn.commit()
                logger = logging.getLogger(__name__)
                logger.info("Added market column to job_discoveries table")
            except sqlite3.OperationalError as e:
                # Column might already exist from a previous partial migration
                logger = logging.getLogger(__name__)
                logger.debug("Migration error (may be expected): %s", e)

        # Add indexes for performance
        try:
            c.execute("CREATE INDEX IF NOT EXISTS idx_job_discoveries_market ON job_discoveries(market)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_job_discoveries_source ON job_discoveries(source)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_job_discoveries_market_location ON job_discoveries(market, location)")
            conn.commit()
        except sqlite3.OperationalError as e:
            logger = logging.getLogger(__name__)
            logger.debug("Index creation error (may be expected): %s", e)

        # Check if salary columns exist in applications
        c.execute("PRAGMA table_info(applications)")
        app_columns = [row[1] for row in c.fetchall()]

        if "salary_min" not in app_columns:
            try:
                c.execute("ALTER TABLE applications ADD COLUMN salary_min INTEGER")
                conn.commit()
                logger = logging.getLogger(__name__)
                logger.info("Added salary_min column to applications table")
            except sqlite3.OperationalError as e:
                logger = logging.getLogger(__name__)
                logger.debug("Migration error (may be expected): %s", e)

        if "salary_max" not in app_columns:
            try:
                c.execute("ALTER TABLE applications ADD COLUMN salary_max INTEGER")
                conn.commit()
                logger = logging.getLogger(__name__)
                logger.info("Added salary_max column to applications table")
            except sqlite3.OperationalError as e:
                logger = logging.getLogger(__name__)
                logger.debug("Migration error (may be expected): %s", e)

        if "salary_currency" not in app_columns:
            try:
                c.execute("ALTER TABLE applications ADD COLUMN salary_currency TEXT DEFAULT 'USD'")
                conn.commit()
                logger = logging.getLogger(__name__)
                logger.info("Added salary_currency column to applications table")
            except sqlite3.OperationalError as e:
                logger = logging.getLogger(__name__)
                logger.debug("Migration error (may be expected): %s", e)

        conn.close()
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error("Migration failed: %s", e)


class TrackerDB:
    """CRUD operations for the jSeeker application tracker."""

    def __init__(self, db_path: Path = None):
        if db_path is None:
            db_path = _get_db_path()
        self.db_path = db_path
        init_db(db_path)

    def _conn(self) -> sqlite3.Connection:
        """Legacy method for backward compatibility - use _get_conn instead."""
        return self._get_conn()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection with proper timeout and configuration.

        Configured with:
        - 30 second timeout to prevent "database is locked" errors
        - check_same_thread=False for thread safety
        - Row factory for dict-like access
        """
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row

        # Health check: verify connection is usable
        try:
            conn.execute("SELECT 1")
        except sqlite3.Error:
            conn.close()
            # Retry once if health check fails
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row

        return conn

    @contextmanager
    def _transaction(self):
        """Context manager for atomic transactions.

        Yields:
            Tuple of (connection, cursor) for use within the transaction

        Usage:
            with db._transaction() as (conn, cursor):
                cursor.execute("INSERT INTO ...")
                cursor.execute("UPDATE ...")
            # Auto-commits on success, rolls back on exception
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            yield conn, cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Companies ──────────────────────────────────────────────────

    def add_company(self, company: Company) -> int:
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO companies (name, industry, size, detected_ats, careers_url, notes) VALUES (?,?,?,?,?,?)",
            (company.name, company.industry, company.size, company.detected_ats, company.careers_url, company.notes),
        )
        conn.commit()
        row_id = c.lastrowid
        conn.close()
        return row_id

    def get_or_create_company(self, name: str) -> int:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT id FROM companies WHERE name = ?", (name,))
        row = c.fetchone()
        if row:
            conn.close()
            return row["id"]
        c.execute("INSERT INTO companies (name) VALUES (?)", (name,))
        conn.commit()
        row_id = c.lastrowid
        conn.close()
        return row_id

    def update_company_name(self, company_id: int, name: str) -> None:
        """Update company name.

        Args:
            company_id: Company ID to update
            name: New company name
        """
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE companies SET name = ? WHERE id = ?", (name, company_id))
        conn.commit()
        conn.close()

    # ── Applications ──────────────────────────────────────────────

    def add_application(self, app: Application) -> int:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO applications
            (company_id, role_title, jd_text, jd_url, salary_range, salary_min,
             salary_max, salary_currency, location,
             remote_policy, relevance_score, resume_status, application_status,
             job_status, recruiter_name, recruiter_email, recruiter_linkedin, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (app.company_id, app.role_title, app.jd_text, app.jd_url,
             app.salary_range, app.salary_min, app.salary_max, app.salary_currency,
             app.location, app.remote_policy,
             app.relevance_score, app.resume_status.value,
             app.application_status.value, app.job_status.value,
             app.recruiter_name, app.recruiter_email, app.recruiter_linkedin,
             app.notes),
        )
        conn.commit()
        row_id = c.lastrowid
        conn.close()
        return row_id

    def get_application(self, app_id: int) -> Optional[dict]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""SELECT a.*, c.name as company_name
            FROM applications a
            LEFT JOIN companies c ON a.company_id = c.id
            WHERE a.id = ?""", (app_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def list_applications(
        self,
        application_status: str = None,
        resume_status: str = None,
        job_status: str = None,
    ) -> list[dict]:
        conn = self._conn()
        c = conn.cursor()
        query = """SELECT a.*, c.name as company_name,
            (SELECT MAX(r.ats_score) FROM resumes r WHERE r.application_id = a.id) as ats_score
            FROM applications a
            LEFT JOIN companies c ON a.company_id = c.id
            WHERE 1=1"""
        params = []
        if application_status:
            query += " AND a.application_status = ?"
            params.append(application_status)
        if resume_status:
            query += " AND a.resume_status = ?"
            params.append(resume_status)
        if job_status:
            query += " AND a.job_status = ?"
            params.append(job_status)
        query += " ORDER BY a.updated_at DESC"
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_application_status(
        self, app_id: int, field: str, value: str
    ) -> None:
        allowed = {"resume_status", "application_status", "job_status"}
        if field not in allowed:
            raise ValueError(f"Field must be one of {allowed}")
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            f"UPDATE applications SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, app_id),
        )
        conn.commit()
        conn.close()

    _ALLOWED_APP_FIELDS = {
        "role_title", "jd_text", "jd_url", "salary_range",
        "salary_min", "salary_max", "salary_currency", "location",
        "remote_policy", "relevance_score", "resume_status",
        "application_status", "job_status", "job_status_checked_at",
        "applied_date", "last_activity", "recruiter_name",
        "recruiter_email", "recruiter_linkedin", "outreach_sent",
        "outreach_text", "notes",
    }

    def update_application(self, app_id: int, **kwargs) -> None:
        invalid = set(kwargs.keys()) - self._ALLOWED_APP_FIELDS
        if invalid:
            raise ValueError(f"Invalid fields: {invalid}")
        conn = self._conn()
        c = conn.cursor()
        sets = []
        vals = []
        for key, val in kwargs.items():
            sets.append(f"{key} = ?")
            vals.append(val)
        sets.append("updated_at = CURRENT_TIMESTAMP")
        vals.append(app_id)
        c.execute(f"UPDATE applications SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
        conn.close()

    def delete_application(self, app_id: int) -> bool:
        """Delete an application and all associated resumes and files.

        Args:
            app_id: Application ID to delete

        Returns:
            True if deleted, False if not found

        Note:
            This is a CASCADE delete that removes:
            - All associated resumes (and their PDF/DOCX files from disk)
            - The application record
            Does NOT delete the company record (may be used by other applications)
        """
        conn = self._conn()
        c = conn.cursor()

        # First check if application exists
        c.execute("SELECT id FROM applications WHERE id = ?", (app_id,))
        if not c.fetchone():
            conn.close()
            return False

        # Delete all associated resumes and their files
        c.execute("SELECT id FROM resumes WHERE application_id = ?", (app_id,))
        resume_ids = [row[0] for row in c.fetchall()]
        for resume_id in resume_ids:
            # delete_resume handles file deletion
            self.delete_resume(resume_id)

        # Delete the application
        c.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        conn.commit()
        conn.close()

        logger = logging.getLogger(__name__)
        logger.info(f"Deleted application {app_id} and {len(resume_ids)} associated resume(s)")
        return True

    # ── Resumes ────────────────────────────────────────────────────

    def add_resume(self, resume: Resume) -> int:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO resumes
            (application_id, version, template_used, content_json, pdf_path,
             docx_path, ats_score, ats_platform, generation_cost, user_edited)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (resume.application_id, resume.version, resume.template_used,
             resume.content_json, resume.pdf_path, resume.docx_path,
             resume.ats_score, resume.ats_platform, resume.generation_cost,
             resume.user_edited),
        )
        conn.commit()
        row_id = c.lastrowid
        conn.close()
        return row_id

    def get_resumes_for_application(self, app_id: int) -> list[dict]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM resumes WHERE application_id = ? ORDER BY version DESC", (app_id,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── API Costs ──────────────────────────────────────────────────

    def log_cost(self, cost: APICost) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO api_costs
            (model, task, input_tokens, output_tokens, cache_tokens, cost_usd)
            VALUES (?,?,?,?,?,?)""",
            (cost.model, cost.task, cost.input_tokens, cost.output_tokens,
             cost.cache_tokens, cost.cost_usd),
        )
        conn.commit()
        conn.close()

    def get_monthly_cost(self) -> float:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""SELECT COALESCE(SUM(cost_usd), 0) as total
            FROM api_costs
            WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')""")
        row = c.fetchone()
        conn.close()
        return row["total"] if row else 0.0

    # ── Job Discoveries ────────────────────────────────────────────

    def add_discovery(self, discovery: JobDiscovery) -> Optional[int]:
        conn = self._conn()
        c = conn.cursor()
        normalized_status = _normalize_discovery_status(discovery.status)
        try:
            c.execute("""INSERT INTO job_discoveries
                (title, company, location, salary_range, url, source, market,
                 posting_date, search_tags, status)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (discovery.title, discovery.company, discovery.location,
                 discovery.salary_range, discovery.url, discovery.source, discovery.market,
                 str(discovery.posting_date) if discovery.posting_date else None,
                 discovery.search_tags, normalized_status),
            )
            conn.commit()
            row_id = c.lastrowid
        except sqlite3.IntegrityError:
            row_id = None  # Duplicate URL
        conn.close()
        return row_id

    def list_discoveries(
        self,
        status: str = None,
        search: str = "",
        market: str = None,
        location: str = None,
        source: str = None
    ) -> list[dict]:
        """List job discoveries with optional filters.

        Args:
            status: Filter by discovery status (new, starred, dismissed, imported)
            search: Search across title, company, location, source, tags, url
            market: Filter by market code (us, mx, ca, uk, es, de)
            location: Filter by location (partial match)
            source: Filter by source (indeed, linkedin, wellfound)
        """
        conn = self._conn()
        c = conn.cursor()
        query = "SELECT * FROM job_discoveries WHERE 1=1"
        params: list[str] = []

        if status:
            normalized = _normalize_discovery_status(status)
            query += " AND LOWER(TRIM(status)) = LOWER(TRIM(?))"
            params.append(normalized)

        if market:
            query += " AND LOWER(TRIM(COALESCE(market, ''))) = LOWER(TRIM(?))"
            params.append(market)

        if location:
            query += " AND LOWER(COALESCE(location, '')) LIKE ?"
            params.append(f"%{location.lower()}%")

        if source:
            query += " AND LOWER(TRIM(COALESCE(source, ''))) = LOWER(TRIM(?))"
            params.append(source)

        normalized_search = (search or "").strip().lower()
        if normalized_search:
            like = f"%{normalized_search}%"
            query += (
                " AND ("
                "LOWER(COALESCE(title, '')) LIKE ? OR "
                "LOWER(COALESCE(company, '')) LIKE ? OR "
                "LOWER(COALESCE(location, '')) LIKE ? OR "
                "LOWER(COALESCE(source, '')) LIKE ? OR "
                "LOWER(COALESCE(market, '')) LIKE ? OR "
                "LOWER(COALESCE(search_tags, '')) LIKE ? OR "
                "LOWER(COALESCE(url, '')) LIKE ?"
                ")"
            )
            params.extend([like, like, like, like, like, like, like])

        query += " ORDER BY discovered_at DESC"
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_discovery_status(self, discovery_id: int, status: str) -> None:
        normalized = _normalize_discovery_status(status)
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE job_discoveries SET status = ? WHERE id = ?", (normalized, discovery_id))
        conn.commit()
        conn.close()

    # ── Search Tags ────────────────────────────────────────────────

    def add_search_tag(self, tag: str) -> Optional[int]:
        normalized_tag = _normalize_search_tag(tag)
        if not normalized_tag:
            return None

        conn = self._conn()
        c = conn.cursor()

        c.execute("SELECT id FROM search_tags WHERE LOWER(tag) = LOWER(?)", (normalized_tag,))
        if c.fetchone():
            conn.close()
            return None

        try:
            c.execute("INSERT INTO search_tags (tag, active) VALUES (?, 1)", (normalized_tag,))
            conn.commit()
            row_id = c.lastrowid
        except sqlite3.IntegrityError:
            row_id = None
        conn.close()
        return row_id

    def list_search_tags(self, active_only: bool = True) -> list[dict]:
        conn = self._conn()
        c = conn.cursor()
        if active_only:
            c.execute(
                "SELECT * FROM search_tags "
                "WHERE COALESCE(CAST(active AS INTEGER), 1) = 1 "
                "ORDER BY LOWER(tag)"
            )
        else:
            c.execute(
                "SELECT * FROM search_tags ORDER BY "
                "COALESCE(CAST(active AS INTEGER), 1) DESC, LOWER(tag)"
            )
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def toggle_search_tag(self, tag_id: int, active: bool) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE search_tags SET active = ? WHERE id = ?", (1 if active else 0, tag_id))
        conn.commit()
        conn.close()

    # ── Tag Weights ────────────────────────────────────────────────

    def set_tag_weight(self, tag: str, weight: int) -> None:
        """Set or update the weight for a search tag (1-100 scale)."""
        normalized_tag = _normalize_search_tag(tag)
        if not normalized_tag:
            return

        weight = max(1, min(100, weight))  # Clamp to 1-100

        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO tag_weights
            (tag, weight, created_at, updated_at)
            VALUES (?, ?, COALESCE((SELECT created_at FROM tag_weights WHERE tag = ?), CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)""",
            (normalized_tag, weight, normalized_tag),
        )
        conn.commit()
        conn.close()

    def get_tag_weight(self, tag: str) -> int:
        """Get the weight for a tag (default 50 if not set)."""
        normalized_tag = _normalize_search_tag(tag)
        if not normalized_tag:
            return 50

        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT weight FROM tag_weights WHERE tag = ?", (normalized_tag,))
        row = c.fetchone()
        conn.close()
        return row["weight"] if row else 50

    def list_tag_weights(self) -> list[dict]:
        """List all tag weights."""
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM tag_weights ORDER BY weight DESC, tag ASC")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_tag_weight(self, tag: str) -> None:
        """Delete a tag weight (resets to default 50)."""
        normalized_tag = _normalize_search_tag(tag)
        if not normalized_tag:
            return

        conn = self._conn()
        c = conn.cursor()
        c.execute("DELETE FROM tag_weights WHERE tag = ?", (normalized_tag,))
        conn.commit()
        conn.close()

    # ── Search Sessions ────────────────────────────────────────────

    def create_search_session(self, tags: list[str], markets: list[str], sources: list[str]) -> int:
        """Create a new search session."""
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO search_sessions
            (tags, markets, sources, status, total_found)
            VALUES (?, ?, ?, 'active', 0)""",
            (json.dumps(tags), json.dumps(markets), json.dumps(sources)),
        )
        conn.commit()
        session_id = c.lastrowid
        conn.close()
        return session_id

    def update_search_session(
        self,
        session_id: int,
        status: str = None,
        total_found: int = None,
        limit_reached: bool = None
    ) -> None:
        """Update search session status."""
        conn = self._conn()
        c = conn.cursor()

        updates = []
        params = []

        if status:
            updates.append("status = ?")
            params.append(status)
            if status in ("completed", "stopped"):
                updates.append("completed_at = CURRENT_TIMESTAMP")

        if total_found is not None:
            updates.append("total_found = ?")
            params.append(total_found)

        if limit_reached is not None:
            updates.append("limit_reached = ?")
            params.append(1 if limit_reached else 0)

        if updates:
            params.append(session_id)
            query = f"UPDATE search_sessions SET {', '.join(updates)} WHERE id = ?"
            c.execute(query, params)
            conn.commit()

        conn.close()

    def get_search_session(self, session_id: int) -> Optional[dict]:
        """Get search session details."""
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM search_sessions WHERE id = ?", (session_id,))
        row = c.fetchone()
        conn.close()
        if row:
            result = dict(row)
            result["tags"] = json.loads(result.get("tags", "[]"))
            result["markets"] = json.loads(result.get("markets", "[]"))
            result["sources"] = json.loads(result.get("sources", "[]"))
            return result
        return None

    # ── Pipeline Integration ───────────────────────────────────────

    def create_from_pipeline(self, result) -> dict:
        """Create application, resume, and company from a PipelineResult.

        Args:
            result: PipelineResult from pipeline.run_pipeline()

        Returns:
            Dict with company_id, application_id, resume_id
        """
        import json
        from jseeker.models import Application, Resume, ResumeStatus, ApplicationStatus, JobStatus

        # Get or create company
        company_id = self.get_or_create_company(result.company or "Unknown")

        # Create application with defaults
        app = Application(
            company_id=company_id,
            role_title=result.role or "Unknown",
            jd_text=result.parsed_jd.raw_text,
            jd_url=result.parsed_jd.jd_url,
            location=result.parsed_jd.location,
            remote_policy=result.parsed_jd.remote_policy,
            salary_range=result.parsed_jd.salary_range,
            salary_min=result.parsed_jd.salary_min,
            salary_max=result.parsed_jd.salary_max,
            salary_currency=result.parsed_jd.salary_currency,
            relevance_score=result.match_result.relevance_score,
            resume_status=ResumeStatus.GENERATED,
            application_status=ApplicationStatus.NOT_APPLIED,
            job_status=JobStatus.ACTIVE,
        )
        app_id = self.add_application(app)

        # Create resume entry
        resume = Resume(
            application_id=app_id,
            template_used=result.match_result.template_type.value,
            content_json=json.dumps(result.adapted_resume.model_dump(), default=str),
            pdf_path=result.pdf_path,
            docx_path=result.docx_path,
            ats_score=result.ats_score.overall_score,
            ats_platform=result.parsed_jd.detected_ats.value,
            generation_cost=result.total_cost,
        )
        resume_id = self.add_resume(resume)

        return {"company_id": company_id, "application_id": app_id, "resume_id": resume_id}

    def list_all_resumes(self) -> list[dict]:
        """List all resumes with application and company info.

        Returns:
            List of dicts containing resume data with joined application and company info
        """
        conn = self._conn()
        c = conn.cursor()
        c.execute("""SELECT r.*, a.role_title, a.jd_url, a.company_id, c.name as company_name
            FROM resumes r
            LEFT JOIN applications a ON r.application_id = a.id
            LEFT JOIN companies c ON a.company_id = c.id
            ORDER BY r.created_at DESC""")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_next_resume_version(self, application_id: int) -> int:
        """Get next version number for a resume.

        Args:
            application_id: Application ID to get next version for

        Returns:
            Next version number (1 if no resumes exist)
        """
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT MAX(version) as max_v FROM resumes WHERE application_id = ?", (application_id,))
        row = c.fetchone()
        conn.close()
        return (row["max_v"] or 0) + 1

    def delete_resume(self, resume_id: int) -> bool:
        """Delete a resume and its files from disk.

        Args:
            resume_id: Resume ID to delete

        Returns:
            True if deleted, False if not found
        """
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT pdf_path, docx_path FROM resumes WHERE id = ?", (resume_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False

        # Delete files
        from pathlib import Path
        for path_str in [row["pdf_path"], row["docx_path"]]:
            if path_str:
                p = Path(path_str)
                p.unlink(missing_ok=True)

        c.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
        conn.commit()
        conn.close()
        return True

    def is_url_known(self, url: str) -> bool:
        """Check if a URL exists in job_discoveries or applications.

        Args:
            url: URL to check

        Returns:
            True if URL exists in either table, False otherwise
        """
        if not url:
            return False
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT 1 FROM job_discoveries WHERE url = ?", (url,))
        if c.fetchone():
            conn.close()
            return True
        c.execute("SELECT 1 FROM applications WHERE jd_url = ?", (url,))
        result = c.fetchone() is not None
        conn.close()
        return result

    # ── Stats ──────────────────────────────────────────────────────

    def get_dashboard_stats(self) -> dict:
        conn = self._conn()
        c = conn.cursor()

        c.execute("SELECT COUNT(*) as total FROM applications")
        total = c.fetchone()["total"]

        c.execute("SELECT COUNT(*) as active FROM applications WHERE application_status NOT IN ('rejected','ghosted','withdrawn')")
        active = c.fetchone()["active"]

        c.execute("SELECT AVG(r.ats_score) as avg_score FROM resumes r WHERE r.ats_score > 0")
        row = c.fetchone()
        avg_score = round(row["avg_score"], 1) if row and row["avg_score"] else 0

        c.execute("SELECT COALESCE(SUM(cost_usd), 0) as cost FROM api_costs WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')")
        monthly_cost = c.fetchone()["cost"]

        conn.close()
        return {
            "total_applications": total,
            "active_applications": active,
            "avg_ats_score": avg_score,
            "monthly_cost_usd": round(monthly_cost, 2),
        }

    # ── Batch Processing ───────────────────────────────────────────

    def create_batch_job(self, total_count: int) -> str:
        """Create a new batch job entry.

        Args:
            total_count: Total number of URLs in batch

        Returns:
            Batch ID (UUID)
        """
        import uuid
        import logging
        logger = logging.getLogger(__name__)

        batch_id = str(uuid.uuid4())[:8]
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO batch_jobs (id, total_count, status) VALUES (?, ?, ?)",
            (batch_id, total_count, "running"),
        )
        conn.commit()
        conn.close()
        logger.info(f"Created batch job {batch_id} with {total_count} URLs")
        return batch_id

    def update_batch_job(
        self,
        batch_id: str,
        status: str = None,
        completed_at: datetime = None,
        completed_count: int = None,
        failed_count: int = None,
        skipped_count: int = None,
    ) -> None:
        """Update batch job status and counts.

        Args:
            batch_id: Batch ID to update
            status: New status (running, completed, stopped)
            completed_at: Completion timestamp
            completed_count: Number of completed jobs
            failed_count: Number of failed jobs
            skipped_count: Number of skipped jobs
        """
        conn = self._get_conn()
        c = conn.cursor()

        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at.isoformat())
        if completed_count is not None:
            updates.append("completed_count = ?")
            params.append(completed_count)
        if failed_count is not None:
            updates.append("failed_count = ?")
            params.append(failed_count)
        if skipped_count is not None:
            updates.append("skipped_count = ?")
            params.append(skipped_count)

        if not updates:
            conn.close()
            return

        params.append(batch_id)
        query = f"UPDATE batch_jobs SET {', '.join(updates)} WHERE id = ?"
        c.execute(query, params)
        conn.commit()
        conn.close()

    def get_batch_status(self, batch_id: str) -> Optional[dict]:
        """Get batch job status.

        Args:
            batch_id: Batch ID to query

        Returns:
            Dict with batch status or None if not found
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM batch_jobs WHERE id = ?", (batch_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def list_batch_jobs(self, limit: int = 50) -> list[dict]:
        """List recent batch jobs.

        Args:
            limit: Maximum number of batches to return

        Returns:
            List of batch job dicts
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM batch_jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def create_batch_job_item(
        self,
        batch_id: str,
        url: str,
        status: str = "pending",
        error: str = None,
        resume_id: int = None,
        application_id: int = None,
    ) -> int:
        """Create batch job item entry.

        Args:
            batch_id: Parent batch ID
            url: Job URL
            status: Job status (pending, completed, failed, skipped)
            error: Error message if failed
            resume_id: Resume ID if completed
            application_id: Application ID if completed

        Returns:
            Item ID
        """
        conn = self._get_conn()
        c = conn.cursor()

        now = datetime.now().isoformat()
        started_at = now if status != "pending" else None
        completed_at = now if status in ("completed", "failed", "skipped") else None

        c.execute(
            """INSERT INTO batch_job_items
            (batch_id, url, status, error, resume_id, application_id, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (batch_id, url, status, error, resume_id, application_id, started_at, completed_at),
        )
        conn.commit()
        item_id = c.lastrowid
        conn.close()
        return item_id

    def list_batch_job_items(self, batch_id: str) -> list[dict]:
        """List all items for a batch job.

        Args:
            batch_id: Batch ID to query

        Returns:
            List of batch job item dicts
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM batch_job_items WHERE batch_id = ? ORDER BY created_at",
            (batch_id,),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Saved Searches ─────────────────────────────────────────────

    def save_search_config(
        self,
        name: str,
        tag_weights: dict[str, int],
        markets: list[str] = None,
        sources: list[str] = None,
        location: str = None
    ) -> int:
        """Save a search configuration for later reuse.

        Args:
            name: Name for this saved search (must be unique)
            tag_weights: Dict mapping tag names to weights (1-100)
            markets: List of market codes to search
            sources: List of sources to search
            location: Location filter string

        Returns:
            Saved search ID

        Raises:
            sqlite3.IntegrityError: If a search with this name already exists
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT INTO saved_searches (name, tag_weights, markets, sources, location)
            VALUES (?, ?, ?, ?, ?)""",
            (
                name,
                json.dumps(tag_weights),
                json.dumps(markets or []),
                json.dumps(sources or []),
                location or ""
            )
        )
        conn.commit()
        saved_id = c.lastrowid
        conn.close()
        return saved_id

    def list_saved_searches(self) -> list[dict]:
        """List all saved search configurations.

        Returns:
            List of dicts with id, name, tag_weights, markets, sources, location, created_at, updated_at
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM saved_searches ORDER BY name")
        rows = c.fetchall()
        conn.close()
        result = []
        for row in rows:
            d = dict(row)
            d["tag_weights"] = json.loads(d.get("tag_weights", "{}"))
            d["markets"] = json.loads(d.get("markets", "[]"))
            d["sources"] = json.loads(d.get("sources", "[]"))
            result.append(d)
        return result

    def get_saved_search(self, search_id: int) -> Optional[dict]:
        """Get a saved search configuration by ID.

        Args:
            search_id: Saved search ID

        Returns:
            Dict with search configuration or None if not found
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM saved_searches WHERE id = ?", (search_id,))
        row = c.fetchone()
        conn.close()
        if row:
            d = dict(row)
            d["tag_weights"] = json.loads(d.get("tag_weights", "{}"))
            d["markets"] = json.loads(d.get("markets", "[]"))
            d["sources"] = json.loads(d.get("sources", "[]"))
            return d
        return None

    def delete_saved_search(self, search_id: int) -> bool:
        """Delete a saved search configuration.

        Args:
            search_id: Saved search ID to delete

        Returns:
            True if deleted, False if not found
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM saved_searches WHERE id = ?", (search_id,))
        deleted = c.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def update_saved_search(
        self,
        search_id: int,
        name: str = None,
        tag_weights: dict[str, int] = None,
        markets: list[str] = None,
        sources: list[str] = None,
        location: str = None
    ) -> bool:
        """Update a saved search configuration.

        Args:
            search_id: Saved search ID to update
            name: New name (optional)
            tag_weights: New tag weights (optional)
            markets: New markets list (optional)
            sources: New sources list (optional)
            location: New location filter (optional)

        Returns:
            True if updated, False if not found
        """
        conn = self._get_conn()
        c = conn.cursor()

        updates = ["updated_at = CURRENT_TIMESTAMP"]
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if tag_weights is not None:
            updates.append("tag_weights = ?")
            params.append(json.dumps(tag_weights))
        if markets is not None:
            updates.append("markets = ?")
            params.append(json.dumps(markets))
        if sources is not None:
            updates.append("sources = ?")
            params.append(json.dumps(sources))
        if location is not None:
            updates.append("location = ?")
            params.append(location)

        if not updates or len(updates) == 1:  # Only timestamp update
            conn.close()
            return False

        params.append(search_id)
        query = f"UPDATE saved_searches SET {', '.join(updates)} WHERE id = ?"
        c.execute(query, params)
        updated = c.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    # ── CSV Export/Import ──────────────────────────────────────────

    def export_csv(self, output_path: Path) -> Path:
        """Export all applications to CSV."""
        import csv
        apps = self.list_applications()
        if not apps:
            return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=apps[0].keys())
            writer.writeheader()
            writer.writerows(apps)
        return output_path

    def import_csv(self, csv_path: Path) -> int:
        """Import applications from CSV. Returns count of imported rows."""
        import csv
        count = 0
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                company_id = self.get_or_create_company(row.get("company_name", "Unknown"))
                app = Application(
                    company_id=company_id,
                    role_title=row.get("role_title", "Unknown"),
                    jd_url=row.get("jd_url", ""),
                    location=row.get("location", ""),
                    notes=row.get("notes", ""),
                )
                self.add_application(app)
                count += 1
        return count


# Module-level singleton
tracker_db = TrackerDB()
