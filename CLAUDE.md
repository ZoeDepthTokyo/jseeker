# PROTEUS — The Shape-Shifting Resume Engine

## Role
PROTEUS adapts structured resume content to match job descriptions, scores ATS compliance per platform, renders PDF + DOCX, generates recruiter outreach, and tracks applications. It is a GAIA ecosystem product.

## Constitutional Constraints
1. Never invent or hallucinate experience, metrics, or achievements — only adapt real content from resume blocks
2. All LLM calls must be cost-tracked and logged
3. Resume blocks are the single source of truth — adaptation rewrites phrasing, never fabricates
4. ATS scoring must be platform-aware (Greenhouse, Workday, Lever, iCIMS, Ashby, Taleo)
5. User edits are sacred — the feedback system learns from them, never overrides

## Directory Structure
proteus/ — main package (models, llm, jd_parser, matcher, adapter, ats_scorer, renderer, outreach, tracker, job_discovery, job_monitor, feedback)
data/ — YAML resume blocks, HTML/CSS templates, prompt templates, ATS profiles, SQLite DB
ui/ — Streamlit app (dashboard, new_resume, editor, tracker, job_discovery, block_manager, analytics)
tests/ — pytest suite
docs/ — PRD, architecture, user guide, ATS research, changelog
output/ — generated resumes (gitignored)

## Coding Patterns
- All data models in proteus/models.py (Pydantic v2)
- LLM calls via proteus/llm.py (Haiku for cheap tasks, Sonnet for quality)
- Resume content in data/resume_blocks/*.yaml (tagged per template A/B/C)
- HTML templates rendered via Jinja2 + Playwright for PDF
- SQLite for persistence (proteus.db)
- Prompt templates in data/prompts/*.txt with {variable} placeholders

## Integration Points
- **MYCEL**: LLM client via integrations/mycel_bridge.py (fallback to direct Anthropic SDK)
- **ARGUS**: Build + runtime telemetry via integrations/argus_telemetry.py
- **MNEMIS**: Pattern storage via integrations/mnemis_bridge.py (Phase 3+)

## Testing
pytest tests/ --cov=proteus

## Key Files
- proteus/adapter.py — Core value: Claude-powered resume content adaptation
- proteus/renderer.py — PDF (Playwright) + DOCX (python-docx) generation
- proteus/llm.py — Claude API wrapper with model routing and caching
- proteus/models.py — All Pydantic data types
- ui/pages/2_new_resume.py — Main user workflow wizard

## DO NOT
- Invent experience or metrics not in resume_blocks YAML
- Use Opus model at runtime (budget constraint)
- Store API keys anywhere except .env
- Commit .env, output/, or proteus.db
