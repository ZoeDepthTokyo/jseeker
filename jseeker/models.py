"""jSeeker Pydantic v2 data models."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

# ── Custom Exceptions ──────────────────────────────────────────────


class AdaptationError(Exception):
    """Raised when resume adaptation fails (JSON parse, validation, etc.)."""

    pass


class RenderError(Exception):
    """Raised when PDF or DOCX rendering fails after retries."""

    pass


# ── Enums ──────────────────────────────────────────────────────────────


class TemplateType(str, Enum):
    AI_UX = "ai_ux"
    AI_PRODUCT = "ai_product"
    HYBRID = "hybrid"


class ResumeStatus(str, Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    EDITED = "edited"
    EXPORTED = "exported"
    SUBMITTED = "submitted"


class ApplicationStatus(str, Enum):
    NOT_APPLIED = "not_applied"
    EASY_APPLY = "easy_apply"
    APPLIED = "applied"
    SCREENING = "screening"
    PHONE_SCREEN = "phone_screen"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    GHOSTED = "ghosted"
    WITHDRAWN = "withdrawn"


class JobStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"
    REPOSTED = "reposted"


class ATSPlatform(str, Enum):
    GREENHOUSE = "greenhouse"
    WORKDAY = "workday"
    LEVER = "lever"
    ICIMS = "icims"
    ASHBY = "ashby"
    TALEO = "taleo"
    UNKNOWN = "unknown"


class DiscoveryStatus(str, Enum):
    NEW = "new"
    STARRED = "starred"
    DISMISSED = "dismissed"
    IMPORTED = "imported"


class AttemptStatus(str, Enum):
    """Status of an auto-apply attempt."""

    # Active states
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    # Terminal success states
    APPLIED_VERIFIED = "applied_verified"
    APPLIED_SOFT = "applied_soft"
    # Terminal failure states
    FAILED_PERMANENT = "failed_permanent"
    # Skip states
    SKIPPED_UNSUPPORTED_ATS = "skipped_unsupported_ats"
    SKIPPED_LINKEDIN = "skipped_linkedin"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_ERROR_PATTERN = "skipped_error_pattern"
    # Pause states (non-terminal, awaiting user)
    PAUSED_CAPTCHA = "paused_captcha"
    PAUSED_2FA = "paused_2fa"
    PAUSED_VERIFICATION_REQUIRED = "paused_verification_required"
    PAUSED_ADDITIONAL_DOCS_REQUIRED = "paused_additional_docs_required"
    PAUSED_UNKNOWN_QUESTION = "paused_unknown_question"
    PAUSED_SALARY_QUESTION = "paused_salary_question"
    PAUSED_UNKNOWN_FIELD = "paused_unknown_field"
    PAUSED_LOGIN_FAILED = "paused_login_failed"
    PAUSED_AMBIGUOUS_RESULT = "paused_ambiguous_result"
    PAUSED_MAX_RETRIES = "paused_max_retries"
    PAUSED_COST_CAP = "paused_cost_cap"
    PAUSED_STUCK = "paused_stuck"
    PAUSED_TIMEOUT = "paused_timeout"
    PAUSED_SELECTOR_FAILED = "paused_selector_failed"
    PAUSED_POPUP_BLOCKING = "paused_popup_blocking"
    PAUSED_PARTIAL = "paused_partial"
    PAUSED_MAX_STEPS = "paused_max_steps"


# ── JD Models ──────────────────────────────────────────────────────────


class JDRequirement(BaseModel):
    """A single requirement extracted from a JD."""

    text: str
    category: str = ""  # "hard_skill", "soft_skill", "experience", "education"
    priority: str = "required"  # "required", "preferred", "nice_to_have"
    keywords: list[str] = Field(default_factory=list)


class ParsedJD(BaseModel):
    """Structured representation of a job description."""

    raw_text: str = ""
    pruned_text: str = ""
    title: str = ""
    company: str = ""
    seniority: str = ""
    location: str = ""
    remote_policy: str = ""
    salary_range: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    role_exp: str = ""  # Years of experience in role (e.g., "7+ years")
    management_exp: str = ""  # Years of management experience (e.g., "2+ years")
    requirements: list[JDRequirement] = Field(default_factory=list)
    ats_keywords: list[str] = Field(default_factory=list)
    culture_signals: list[str] = Field(default_factory=list)
    detected_ats: ATSPlatform = ATSPlatform.UNKNOWN
    jd_url: str = ""
    alternate_source_url: str = ""  # URL where full JD was fetched (if different from jd_url)
    language: str = "en"  # "en" or "es" — auto-detected from JD
    market: str = "us"  # "us", "mx", "ca", "uk", "es", "dk", "fr"
    all_locations: list[str] = Field(default_factory=list)  # All location mentions found in JD text
    source_market: str = ""  # Market inferred from job source/listing location


# ── Resume Block Models ────────────────────────────────────────────────


class ContactInfo(BaseModel):
    full_name: str
    display_name: str = ""
    email: str = ""
    phone: str = ""
    locations: list[str] = Field(default_factory=list)
    website: str = ""
    linkedin: str = ""
    youtube: str = ""
    languages: list[dict] = Field(default_factory=list)


class ExperienceBullet(BaseModel):
    text: str
    template_tags: list[TemplateType] = Field(default_factory=list)


class ExperienceBlock(BaseModel):
    company: str
    role: str
    start: str
    end: Optional[str] = None
    location: str = ""
    tags: list[str] = Field(default_factory=list)
    bullets: dict[str, list[str]] = Field(default_factory=dict)
    additional_bullets: list[str] = Field(default_factory=list)


class SkillItem(BaseModel):
    name: str
    ats_keywords: list[str] = Field(default_factory=list)


class SkillCategory(BaseModel):
    display_name: str
    items: list[SkillItem] = Field(default_factory=list)


class Award(BaseModel):
    name: str
    category: str = ""


class Education(BaseModel):
    institution: str
    degree: Optional[str] = None
    field: str = ""
    start: str = ""
    end: str = ""


class Certification(BaseModel):
    name: str


class ResumeCorpus(BaseModel):
    """Complete resume content loaded from YAML blocks."""

    contact: ContactInfo
    summaries: dict[str, str] = Field(default_factory=dict)
    experience: list[ExperienceBlock] = Field(default_factory=list)
    skills: dict[str, SkillCategory] = Field(default_factory=dict)
    awards: list[Award] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    early_career: list[dict] = Field(default_factory=list)


# ── Matching & Adaptation ─────────────────────────────────────────────


class MatchResult(BaseModel):
    """Result of matching resume blocks against a JD."""

    template_type: TemplateType
    relevance_score: float = 0.0
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    gap_analysis: str = ""
    recommended_experiences: list[str] = Field(default_factory=list)


class AdaptedResume(BaseModel):
    """Fully adapted resume content ready for rendering."""

    summary: str = ""
    experience_blocks: list[dict] = Field(default_factory=list)
    skills_ordered: list[dict] = Field(default_factory=list)
    contact: ContactInfo = Field(default_factory=lambda: ContactInfo(full_name=""))
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    awards: list[Award] = Field(default_factory=list)
    early_career: list[dict] = Field(default_factory=list)
    target_title: str = ""
    template_used: TemplateType = TemplateType.HYBRID


# ── PDF Validation ────────────────────────────────────────────────────


class PDFValidationResult(BaseModel):
    """Result of ATS compliance validation."""

    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str = ""
    metadata: dict = Field(default_factory=dict)


class PipelineResult(BaseModel):
    """Complete pipeline output — all intermediate results for traceability."""

    parsed_jd: ParsedJD
    match_result: MatchResult
    adapted_resume: AdaptedResume
    ats_score: ATSScore
    pdf_path: str = ""
    docx_path: str = ""
    company: str = ""
    role: str = ""
    language: str = "en"  # "en" or "es" — auto-detected from JD
    market: str = "us"  # "us", "mx", "ca", "uk", "es", "dk", "fr"
    total_cost: float = 0.0
    generation_timestamp: Optional[datetime] = None
    pdf_validation: Optional[PDFValidationResult] = None


# ── ATS Scoring ────────────────────────────────────────────────────────


class ATSScore(BaseModel):
    """ATS compliance score for a resume against a JD."""

    overall_score: int = 0  # 0-100
    keyword_match_rate: float = 0.0
    format_compliance: float = 0.0
    section_presence: float = 0.0
    bullet_structure: float = 0.0
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    platform: ATSPlatform = ATSPlatform.UNKNOWN
    recommended_format: str = "both"  # "pdf", "docx", "both"
    format_reason: str = ""


# ── Outreach ───────────────────────────────────────────────────────────


class OutreachMessage(BaseModel):
    """Generated recruiter outreach message."""

    recruiter_name: str = ""
    recruiter_email: str = ""
    recruiter_linkedin: str = ""
    subject: str = ""
    body: str = ""
    channel: str = "email"  # "email" or "linkedin"


class IntelligenceReport(BaseModel):
    """JD corpus intelligence analysis result."""

    jd_hash: str = ""
    ideal_profile: str = ""
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    salary_angle: str = ""
    keyword_coverage: float = 0.0
    salary_insight: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    # Glassbox: analysis inputs for transparency
    input_skills: list[str] = Field(default_factory=list)
    keyword_matches: list[str] = Field(default_factory=list)
    keyword_misses: list[str] = Field(default_factory=list)


# ── Tracker ────────────────────────────────────────────────────────────


class Company(BaseModel):
    id: Optional[int] = None
    name: str
    industry: str = ""
    size: str = ""
    detected_ats: str = ""
    careers_url: str = ""
    notes: str = ""
    created_at: Optional[datetime] = None


class Application(BaseModel):
    id: Optional[int] = None
    company_id: Optional[int] = None
    company_name: str = ""
    role_title: str
    jd_text: str = ""
    jd_url: str = ""
    salary_range: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    role_exp: str = ""
    management_exp: str = ""
    location: str = ""
    remote_policy: str = ""
    relevance_score: float = 0.0
    resume_status: ResumeStatus = ResumeStatus.DRAFT
    application_status: ApplicationStatus = ApplicationStatus.NOT_APPLIED
    job_status: JobStatus = JobStatus.ACTIVE
    job_status_checked_at: Optional[datetime] = None
    applied_date: Optional[date] = None
    last_activity: Optional[date] = None
    recruiter_name: str = ""
    recruiter_email: str = ""
    recruiter_linkedin: str = ""
    outreach_sent: bool = False
    outreach_text: str = ""
    notes: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Resume(BaseModel):
    id: Optional[int] = None
    application_id: Optional[int] = None
    version: int = 1
    template_used: str = ""
    content_json: str = ""
    pdf_path: str = ""
    docx_path: str = ""
    ats_score: int = 0
    ats_platform: str = ""
    generation_cost: float = 0.0
    user_edited: bool = False
    created_at: Optional[datetime] = None


class APICost(BaseModel):
    id: Optional[int] = None
    timestamp: Optional[datetime] = None
    model: str = ""
    task: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    cost_usd: float = 0.0


class JobDiscovery(BaseModel):
    id: Optional[int] = None
    title: str
    company: str = ""
    location: str = ""
    salary_range: str = ""
    url: str = ""
    source: str = ""  # Clean source: "indeed", "linkedin", "wellfound" (no market suffix)
    market: str = ""  # Separate market field: "us", "mx", "ca", "uk", "es", "de"
    posting_date: Optional[date] = None
    search_tags: str = ""
    search_tag_weights: dict[str, int] = {}  # Tag weights for ranking (not persisted to DB)
    resume_match_score: float = 0.0  # Resume library content match score (not persisted to DB)
    composite_score: float = 0.0  # Composite relevance score (not persisted to DB)
    tag_weight_contribution: float = (
        0.0  # Tag weight component of composite score (not persisted to DB)
    )
    resume_match_contribution: float = (
        0.0  # Resume match component of composite score (not persisted to DB)
    )
    freshness_contribution: float = (
        0.0  # Freshness bonus component of composite score (not persisted to DB)
    )
    status: DiscoveryStatus = DiscoveryStatus.NEW
    imported_application_id: Optional[int] = None
    discovered_at: Optional[datetime] = None


class SearchTag(BaseModel):
    id: Optional[int] = None
    tag: str
    active: bool = True
    created_at: Optional[datetime] = None


# ── Auto-Apply Models ──────────────────────────────────────────────


class VerificationResult(BaseModel):
    """Result of post-submission verification."""

    is_verified: bool
    signal_matched: Optional[str] = None
    confidence: str  # "hard" | "soft" | "none"
    confirmation_text: Optional[str] = None
    confirmation_url: Optional[str] = None
    error_banners: list[str] = Field(default_factory=list)
    form_still_visible: bool = False
    screenshot_path: Optional[Path] = None
    reason: str = ""


class AttemptResult(BaseModel):
    """Result of a single auto-apply attempt."""

    status: AttemptStatus = AttemptStatus.QUEUED
    screenshots: list[str] = Field(default_factory=list)
    confirmation_text: Optional[str] = None
    confirmation_url: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
    steps_taken: int = 0
    duration_seconds: float = 0.0
    fields_filled: dict[str, str] = Field(default_factory=dict)
    cost_usd: float = 0.0


class RateLimitConfig(BaseModel):
    """Rate limiting configuration for auto-apply."""

    max_per_hour: int = 10
    max_per_day: int = 50
    per_employer_per_day: int = 3
    cooldown_seconds: int = 120
    max_cost_per_day_usd: float = 5.0
    page_load_timeout_ms: int = 30000
    page_load_retry_timeout_ms: int = 60000


class BatchSummary(BaseModel):
    """Summary of a batch auto-apply run."""

    total: int = 0
    verified: int = 0
    soft: int = 0
    paused: int = 0
    failed: int = 0
    skipped: int = 0
    stopped_early: bool = False
    stop_reason: Optional[str] = None
    hitl_required: bool = False
    paused_items: list[int] = Field(default_factory=list)


class MonitorDecision(BaseModel):
    """Health check result from ApplyMonitor circuit breaker."""

    should_continue: bool
    pause_reason: Optional[str] = None
    platform_disabled: list[str] = Field(default_factory=list)
    consecutive_failures: int = 0
    daily_count: int = 0
    hourly_count: int = 0
    daily_cost_usd: float = 0.0
    alert_message: Optional[str] = None
