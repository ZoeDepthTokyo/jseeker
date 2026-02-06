"""PROTEUS Tracker — SQLite CRUD for applications with 3 status pipelines."""

from __future__ import annotations

import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from proteus.models import Application, Company, Resume, APICost, JobDiscovery, SearchTag


def _get_db_path() -> Path:
    from config import settings
    return settings.db_path


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

    conn.commit()
    conn.close()


class TrackerDB:
    """CRUD operations for the PROTEUS application tracker."""

    def __init__(self, db_path: Path = None):
        if db_path is None:
            db_path = _get_db_path()
        self.db_path = db_path
        init_db(db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

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

    # ── Applications ──────────────────────────────────────────────

    def add_application(self, app: Application) -> int:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO applications
            (company_id, role_title, jd_text, jd_url, salary_range, location,
             remote_policy, relevance_score, resume_status, application_status,
             job_status, recruiter_name, recruiter_email, recruiter_linkedin, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (app.company_id, app.role_title, app.jd_text, app.jd_url,
             app.salary_range, app.location, app.remote_policy,
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
        query = """SELECT a.*, c.name as company_name
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
            f"UPDATE applications SET {field} = ?, updated_at = ? WHERE id = ?",
            (value, datetime.now().isoformat(), app_id),
        )
        conn.commit()
        conn.close()

    _ALLOWED_APP_FIELDS = {
        "role_title", "jd_text", "jd_url", "salary_range", "location",
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
        sets.append("updated_at = ?")
        vals.append(datetime.now().isoformat())
        vals.append(app_id)
        c.execute(f"UPDATE applications SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
        conn.close()

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
        try:
            c.execute("""INSERT INTO job_discoveries
                (title, company, location, salary_range, url, source,
                 posting_date, search_tags, status)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (discovery.title, discovery.company, discovery.location,
                 discovery.salary_range, discovery.url, discovery.source,
                 str(discovery.posting_date) if discovery.posting_date else None,
                 discovery.search_tags, discovery.status.value),
            )
            conn.commit()
            row_id = c.lastrowid
        except sqlite3.IntegrityError:
            row_id = None  # Duplicate URL
        conn.close()
        return row_id

    def list_discoveries(self, status: str = None) -> list[dict]:
        conn = self._conn()
        c = conn.cursor()
        if status:
            c.execute("SELECT * FROM job_discoveries WHERE status = ? ORDER BY discovered_at DESC", (status,))
        else:
            c.execute("SELECT * FROM job_discoveries ORDER BY discovered_at DESC")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_discovery_status(self, discovery_id: int, status: str) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE job_discoveries SET status = ? WHERE id = ?", (status, discovery_id))
        conn.commit()
        conn.close()

    # ── Search Tags ────────────────────────────────────────────────

    def add_search_tag(self, tag: str) -> Optional[int]:
        conn = self._conn()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO search_tags (tag) VALUES (?)", (tag,))
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
            c.execute("SELECT * FROM search_tags WHERE active = TRUE ORDER BY tag")
        else:
            c.execute("SELECT * FROM search_tags ORDER BY tag")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def toggle_search_tag(self, tag_id: int, active: bool) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE search_tags SET active = ? WHERE id = ?", (active, tag_id))
        conn.commit()
        conn.close()

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
