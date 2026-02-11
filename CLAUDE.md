# jSeeker -- The Shape-Shifting Resume Engine

## Role
jSeeker (formerly PROTEUS) adapts structured resume content to match job descriptions, scores ATS compliance per platform, renders PDF + DOCX, generates recruiter outreach, and tracks applications. It is a GAIA ecosystem product.

## Quick Start
1. Setup: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
2. Install MYCEL: `pip install -e X:\Projects\_GAIA\_MYCEL`
3. Install browsers: `playwright install`
4. Launch: `python run.py`
5. Open: http://localhost:8502

## Setup & Launch

### Setup
```bash
# Create venv
python -m venv .venv
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
pip install -e X:\Projects\_GAIA\_MYCEL  # MYCEL local package
playwright install  # Browser for PDF rendering
```

### Launch
```bash
# Windows (recommended - clears cache + kills port automatically)
start.bat

# Or manual launch
python run.py                # Full pipeline (recommended)
python launch.py             # Co-launch with ARGUS on :8502 + :8501
streamlit run ui/app.py --server.port 8502  # jSeeker only
```

## Constitutional Constraints
1. Never invent or hallucinate experience, metrics, or achievements -- only adapt real content from resume blocks
2. All LLM calls must be cost-tracked and logged
3. Resume blocks are the single source of truth -- adaptation rewrites phrasing, never fabricates
4. ATS scoring must be platform-aware (Greenhouse, Workday, Lever, iCIMS, Ashby, Taleo)
5. User edits are sacred -- the feedback system learns from them, never overrides

## Directory Structure
jseeker/ -- main package (models, llm, jd_parser, matcher, adapter, ats_scorer, renderer, outreach, tracker, job_discovery, job_monitor, feedback)
data/ -- YAML resume blocks, HTML/CSS templates, prompt templates, ATS profiles, SQLite DB
ui/ -- Streamlit app (dashboard, new_resume, editor, tracker, job_discovery, block_manager, analytics)
tests/ -- pytest suite
docs/ -- PRD, architecture, user guide, ATS research, changelog
output/ -- generated resumes (gitignored)

## Coding Patterns
- All data models in jseeker/models.py (Pydantic v2)
- LLM calls via jseeker/llm.py (Haiku for cheap tasks, Sonnet for quality)
- Resume content in data/resume_blocks/*.yaml (tagged per template A/B/C)
- HTML templates rendered via Jinja2 + Playwright for PDF
- SQLite for persistence (jseeker.db)
- Prompt templates in data/prompts/*.txt with {variable} placeholders

## Integration Points
- **MYCEL**: LLM client via integrations/mycel_bridge.py (fallback to direct Anthropic SDK)
- **ARGUS**: Build + runtime telemetry via integrations/argus_telemetry.py
- **MNEMIS**: Pattern storage via integrations/mnemis_bridge.py (Phase 3+)

## Testing
pytest tests/ --cov=jseeker

## Key Files
- jseeker/adapter.py -- Core value: Claude-powered resume content adaptation
- jseeker/renderer.py -- PDF (Playwright) + DOCX (python-docx) generation
- jseeker/llm.py -- Claude API wrapper with model routing and caching
- jseeker/models.py -- All Pydantic data types
- ui/pages/2_new_resume.py -- Main user workflow wizard

## Gotchas
- **__pycache__ after renames**: Bulk file renames cause stale bytecode. Clear all `__pycache__/` dirs: `find . -name "__pycache__" -type d -exec rm -rf {} +`
- **MYCEL local install**: Must be installed as editable (`-e`) not from PyPI
- **Job Discovery parsers**: Depend on site markup; may need updates if sites change CSS selectors
- **DB auto-migration**: First run auto-renames `proteus.db` -> `jseeker.db` (safe, keeps data)

## DO NOT
- Invent experience or metrics not in resume_blocks YAML
- Use Opus model at runtime (budget constraint)
- Store API keys anywhere except .env
- Commit .env, output/, or jseeker.db