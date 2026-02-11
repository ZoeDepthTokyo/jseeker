# Global Claude Code Instructions (L1 -- Always Loaded)

## Environment
- Windows 11 | PowerShell (prefer over cmd/bash)
- Python 3.10+ | Streamlit | pytest | JSON/YAML/HTML configs

## Top Rules (CRITICAL)
1. Answer verbally first -- only create files if explicitly requested or task requires code
2. Use PowerShell commands: `Get-Process`, `Stop-Process`, `Get-ChildItem`
3. Use Python idioms without asking; bundle doc updates with code changes
4. Use TodoWrite for multi-step tasks; ask before committing to complex plans
5. Never invent experience/metrics in resume blocks -- adapt real content only (jSeeker)

## Subagent Limitations (CRITICAL)
- Subagents CANNOT access MCP tools (Notion, Figma, Pinecone, etc.)
- MCP-dependent work MUST stay in the main context window
- Subagents CAN use: Read, Write, Edit, Glob, Grep
- Always verify subagent file outputs exist after completion

## GAIA Ecosystem
- Registry: `X:\Projects\_GAIA\registry.json`
- Constitution: `X:\Projects\_GAIA\GAIA_BIBLE.md`
- Token budgets: `X:\Projects\_GAIA\token_budget.json`
- Roles: VULCAN creates, LOOM edits, ARGUS monitors, WARDEN governs

## Token Budget Awareness
- Cheap tasks (parsing, extraction): Haiku
- Quality tasks (adaptation, scoring): Sonnet
- Architecture/planning: Opus
- This file is L1 (always loaded). For detailed rules, read `CLAUDE_L2.md`
