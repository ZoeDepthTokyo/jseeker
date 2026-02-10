"""jSeeker Pydantic v2 data models."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
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


# ── JD Models ──────────────────────────────────────────────────────────

class JDRequirement(BaseModel):
    """A single requirement extracted from a JD."""
    text: str
    category: str = ""  # "hard_skill", "soft_skill", "experience", "education"
    priority: str = "required"  # "required", "preferred", "nice_to_have"
    keywords: list[str] = Field(default_factory=list)


class ParsedJD(BaseModel):
    """Structured representation of a job description."""
    raw_text: str
    pruned_text: str = ""
    title: str = ""
    company: str = ""
    seniority: str = ""
    location: str = ""
    remote_policy: str = ""
    salary_range: str = ""
    requirements: list[JDRequirement] = Field(default_factory=list)
    ats_keywords: list[str] = Field(default_factory=list)
    culture_signals: list[str] = Field(default_factory=list)
    detected_ats: ATSPlatform = ATSPlatform.UNKNOWN
    jd_url: str = ""
    language: str = "en"  # "en" or "es" — auto-detected from JD
    market: str = "us"    # "us", "mx", "ca", "uk", "es", "dk", "fr"


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
    market: str = "us"    # "us", "mx", "ca", "uk", "es", "dk", "fr"
    total_cost: float = 0.0
    generation_timestamp: Optional[datetime] = None


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
    source: str = ""
    posting_date: Optional[date] = None
    search_tags: str = ""
    status: DiscoveryStatus = DiscoveryStatus.NEW
    imported_application_id: Optional[int] = None
    discovered_at: Optional[datetime] = None


class SearchTag(BaseModel):
    id: Optional[int] = None
    tag: str
    active: bool = True
    created_at: Optional[datetime] = None
