# Global Claude Code Instructions (L2 -- Detailed Reference)

Load this file when you need extended context beyond what L1 provides.
L1 location: `C:\Users\Fede\.claude\CLAUDE.md`

---

## Response Style -- Full Rules
- When asked for explanations or quick help, respond VERBALLY in chat first
- ONLY create files or enter plan mode if:
  - Explicitly requested ("create a file", "write this")
  - Task clearly requires code changes
- For questions starting with "Explain:", "What is", "How does" -- answer in chat, no files
- Prefer quick, iterative interactions over long plans
- Bundle documentation updates with code changes (don't make separate passes)

## Environment -- Extended
- Platform: Windows 11
- Primary shell: PowerShell (prefer over cmd/bash)
- Use `Get-Process`, `Stop-Process` instead of `netstat`/`taskkill`
- Use `Get-ChildItem` instead of `ls` or `dir` for consistency
- Python 3.10+ across all GAIA projects
- Config formats: JSON (machine), YAML (human-editable), HTML (templates)

## Tech Stack Details
- Primary language: Python with Markdown documentation
- UI framework: Streamlit (all GAIA dashboards and product UIs)
- Testing: pytest with coverage (`--cov=<package>`)
- Data models: Pydantic v2 throughout
- LLM SDKs: anthropic (Claude), openai (GPT), google-generativeai (Gemini)
- Template rendering: Jinja2 + Playwright (PDF), python-docx (DOCX)
- Database: SQLite for local persistence
- Always use Python idioms without asking

## Workflow Preferences
- Quick, iterative interactions preferred
- Ask clarifying questions before committing to complex plans
- Use TodoWrite for multi-step tasks (3+ steps)
- When in doubt, explain approach before implementing
- Bundle related changes (code + tests + docs) in one pass
- For multi-file refactors, confirm scope before starting

## Subagent Limitations (CRITICAL)
- Subagents (Task tool) CANNOT access MCP tools (Notion, Figma, Pinecone, etc.)
- MCP-dependent work MUST be done from the main context window
- Subagents CAN use: Read, Write, Edit, Glob, Grep (Bash needs explicit permission)
- Always verify subagent file outputs exist after completion
- If a task requires MCP + file editing, split: do MCP in main, delegate file work

## GAIA Ecosystem -- Full Reference

### Constitutional Principles
- GAIA is the master layer above all AI projects in the local ecosystem
- It solves fragmentation, lack of governance, and multi-API complexity
- All production projects under git version control
- Memory contracts and promotion protocol enforced
- Layered explainability (4 levels mapped to Growth Rungs)

### Component Roles
| Component | Role | Status |
|-----------|------|--------|
| VULCAN    | Project Creator (The Forge) | Operational |
| LOOM      | Workflow Engine (The Workbench) | Operational |
| ARGUS     | Monitoring + Kanban (The Watchman) | Active |
| MNEMIS    | Cross-Project Memory (Mnemosyne) | Operational |
| MYCEL     | Shared Intelligence Library | Active |
| WARDEN    | Governance & Compliance | Active |
| RAVEN     | Autonomous Research Agent | Defined |
| AURORA    | UX/UI Design Lead | Development |
| ABIS      | Visual System Builder | Planning |

### Key Paths
- Registry: `X:\Projects\_GAIA\registry.json`
- Constitution: `X:\Projects\_GAIA\GAIA_BIBLE.md`
- Mental models: `X:\Projects\_GAIA\mental_models\`
- Logs: `X:\Projects\_GAIA\logs\`
- Token budgets: `X:\Projects\_GAIA\token_budget.json`

### When Working in `X:\Projects\_GAIA\*`
- Follow GAIA constitutional principles (see GAIA_BIBLE.md)
- Reference registry at `X:\Projects\_GAIA\registry.json`
- Respect component boundaries (VULCAN creates, LOOM edits, ARGUS monitors)
- Check VERSION_LOG.md for current phase and version status
- Use WARDEN pre-commit hooks for compliance

## Token Budget Management
- Cheap tasks (JD parsing, bullet extraction, classification): Haiku
- Quality tasks (resume adaptation, ATS scoring, outreach): Sonnet
- Architecture planning, multi-file refactoring, system design: Opus
- All LLM calls must be cost-tracked (jSeeker: `jseeker/llm.py`, GAIA: ARGUS telemetry)
- Monthly budget enforcement exists in jSeeker (`BudgetExceededError`)
- Session costs tracked via `APICost` model and persisted to SQLite
- Runtime telemetry logged to `X:\Projects\_GAIA\logs\jseeker_runtime.jsonl`
- See `X:\Projects\_GAIA\token_budget.json` for per-module budgets
- See `X:\Projects\_GAIA\docs\TOKEN_MANAGEMENT.md` for full strategy

## Git & Commit Guidelines
- Never commit `.env`, `output/`, or database files
- Use conventional commit messages (feat:, fix:, docs:, refactor:, test:)
- Run pre-commit hooks (WARDEN) before pushing
- Keep PRs focused -- one feature/fix per PR
- Include tests with code changes when applicable

## Project-Specific Notes

### jSeeker (PROTEUS)
- Resume blocks are the single source of truth -- never fabricate experience
- LLM calls via `jseeker/llm.py` with Haiku/Sonnet routing
- ATS scoring must be platform-aware (Greenhouse, Workday, Lever, iCIMS, Ashby, Taleo)
- User edits are sacred -- feedback system learns from them, never overrides
- No Opus at runtime (budget constraint)
- Templates in `data/templates/`, blocks in `data/resume_blocks/`

### HART OS
- Deterministic scoring pipeline (no LLM randomness in core scoring)
- OpenAI provider (GPT-4o-mini for cheap, GPT-4o for quality)
- Therapy domain -- extra care with language and sensitivity

### VIA Intelligence
- Multi-provider (Gemini primary, OpenAI, Anthropic)
- RAG-based semantic claims and synthesis
- Investment domain -- accuracy is paramount
