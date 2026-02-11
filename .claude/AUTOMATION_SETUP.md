# Claude Code Automation Setup Guide

This guide documents all implemented automations for jSeeker and provides setup instructions for remaining manual steps.

## ✅ Implemented Automations

### 1. Hooks (`.claude/settings.json`)

#### PostToolUse: Auto-format Python Files
- **Trigger**: After Edit/Write on any `.py` file
- **Action**: Runs Black formatter with `--line-length 100`
- **Benefit**: Automatic code formatting, ensures consistency

#### PreToolUse: Block .env Edits
- **Trigger**: Before Edit/Write on `.env` file
- **Action**: Blocks the operation with error message
- **Benefit**: Prevents accidental credential exposure

### 2. Skills

#### `/resume-qa` — Resume Content Validator
- **Location**: `.claude/skills/resume-qa/SKILL.md`
- **Type**: User-only skill (disable-model-invocation: true)
- **Purpose**: Validates generated resumes trace to source YAML blocks
- **Usage**: `/resume-qa output/resume_latest.pdf`
- **Constitutional check**: Ensures no fabricated experience/metrics

#### `/ats-test` — Quick ATS Scoring
- **Location**: `.claude/skills/ats-test/SKILL.md`
- **Type**: User-only skill
- **Purpose**: Quick ATS compliance scoring across 6 platforms
- **Usage**: `/ats-test output/resume_latest.pdf [--platform greenhouse]`
- **Platforms**: Greenhouse, Workday, Lever, iCIMS, Ashby, Taleo

### 3. Subagents

#### `resume-security-reviewer`
- **Location**: `.claude/agents/resume-security-reviewer.md`
- **Purpose**: Scans for PII leaks, credentials, confidential data
- **Invocation**: Parallel with resume generation workflow
- **Tools**: Read, Grep, Glob

#### `test-runner`
- **Location**: `.claude/agents/test-runner.md`
- **Purpose**: Runs pytest suite in background, reports results
- **Invocation**: After code changes to jseeker/ modules
- **Tools**: Bash, Read
- **Target**: 92/92 tests passing, 80%+ coverage

### 4. Team Configuration

#### `.mcp.json` (MCP Server Registry)
- **Location**: `.mcp.json` (project root)
- **Purpose**: Team-shared MCP server configuration
- **Included**: context7 for live documentation lookup
- **Benefit**: Entire team gets same MCP servers automatically

### 5. Pre-commit Hooks

#### Resume YAML Validation
- **Location**: `.pre-commit-config.yaml`
- **Purpose**: Validates YAML syntax in resume_blocks before commit
- **Files**: `data/resume_blocks/*.yaml`
- **Benefit**: Catches malformed YAML early

---

## 🔧 Manual Setup Required

### 1. Install context7 MCP Server

The context7 MCP is configured in `.mcp.json` but needs first-time setup:

```bash
# context7 will auto-install via npx on first use
# No manual installation needed - just restart Claude Code
```

**What it provides:**
- Live documentation for Anthropic SDK
- Playwright API reference
- Streamlit component docs
- Pydantic v2 patterns
- python-docx usage

**How to test:**
1. Restart Claude Code (to load `.mcp.json`)
2. Ask: "Show me the latest Anthropic SDK prompt caching syntax using context7"
3. Claude should query context7 MCP automatically

### 2. (Optional) Install GitHub MCP Server

For repository operations (PRs, issues, CI status):

**Prerequisites:**
```bash
# Install GitHub CLI (Windows via winget)
winget install GitHub.cli

# Authenticate
gh auth login
```

**Add to `.mcp.json`:**
```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@context7/mcp-server"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "$(gh auth token)"
      }
    }
  }
}
```

**What it provides:**
- Create PRs with formatted descriptions
- Check CI/CD run status
- Manage issues and labels
- Review GitHub Actions workflows

### 3. Test the Hooks

#### Test Black Auto-Format Hook
```bash
# 1. Make a poorly formatted Python file
echo "def test(  ):pass" > test_format.py

# 2. Edit it with Claude
# Ask: "Add a docstring to test_format.py"

# 3. Observe: Black auto-formats after Edit
# Expected: Proper spacing, line breaks
```

#### Test .env Block Hook
```bash
# Ask Claude: "Add a comment to .env file"
# Expected: Hook blocks with message:
# "BLOCKED: .env contains sensitive credentials. Edit manually."
```

### 4. Test the Skills

#### Test `/resume-qa`
```bash
# Generate a test resume first, then:
/resume-qa output/resume_2024-01-15.pdf

# Expected: Report showing all content traced to YAML sources
```

#### Test `/ats-test`
```bash
# Score a generated resume:
/ats-test output/resume_latest.pdf

# Expected: Table with scores for all 6 ATS platforms
```

### 5. Test the Subagents

#### Test `resume-security-reviewer`
```bash
# Ask Claude:
# "Launch the resume-security-reviewer agent to scan output/resume_latest.pdf"

# Expected: Security scan report with PII/credential checks
```

#### Test `test-runner`
```bash
# Ask Claude:
# "Launch test-runner in background to run pytest suite"

# Expected: Background task notification, results when complete
```

---

## 📊 Verification Checklist

- [ ] `.claude/settings.json` exists with 2 hooks (PostToolUse, PreToolUse)
- [ ] `.claude/skills/resume-qa/SKILL.md` created
- [ ] `.claude/skills/ats-test/SKILL.md` created
- [ ] `.claude/agents/resume-security-reviewer.md` created
- [ ] `.claude/agents/test-runner.md` created
- [ ] `.mcp.json` exists with context7 configuration
- [ ] `.pre-commit-config.yaml` includes resume YAML validation
- [ ] Black auto-format hook tested and working
- [ ] .env block hook tested and working
- [ ] context7 MCP server accessible (restart Claude Code)
- [ ] Skills show up in `/` command autocomplete
- [ ] Subagents can be invoked via Task tool

---

## 🚀 Usage Examples

### Resume Generation + Security Check
```
1. Generate resume for JD
2. Launch resume-security-reviewer in parallel
3. Run /resume-qa validation
4. Run /ats-test scoring
5. If all pass, export final PDF
```

### Code Change + Test Workflow
```
1. Make changes to jseeker/adapter.py
2. Black auto-formats on save (via hook)
3. Launch test-runner in background
4. Continue working while tests run
5. Receive test results notification
```

### Documentation Lookup
```
Ask: "Using context7, show me the latest Anthropic SDK streaming syntax"
→ Claude queries context7 MCP for current docs
```

---

## 🎯 Next Steps

### High Priority (Do Now)
1. ✅ Restart Claude Code to load `.mcp.json`
2. ✅ Test Black auto-format hook
3. ✅ Test .env block hook
4. ✅ Verify skills appear in autocomplete

### Medium Priority (Do This Week)
5. ⏳ Implement `/resume-qa` skill logic (Python script)
6. ⏳ Implement `/ats-test` skill logic (Python script)
7. ⏳ Test subagents with real workflows

### Low Priority (Nice to Have)
8. ⏳ Install GitHub MCP (if using PRs/issues)
9. ⏳ Add more custom hooks (e.g., test-on-commit)
10. ⏳ Create additional domain-specific skills

---

## 📖 Documentation

- **Hooks Reference**: See `.claude/settings.json` for current configuration
- **Skills Reference**: See `.claude/skills/*/SKILL.md` for each skill
- **Agents Reference**: See `.claude/agents/*.md` for each agent
- **MCP Reference**: See `.mcp.json` for server configuration

For more information on Claude Code automation:
- Hooks: https://docs.anthropic.com/en/docs/claude-code/hooks
- Skills: https://docs.anthropic.com/en/docs/claude-code/skills
- MCP: https://modelcontextprotocol.io/

---

## 🐛 Troubleshooting

### Hook not running
- Check `.claude/settings.json` syntax (must be valid JSON)
- Verify `black` is installed: `pip install black`
- Check hook command is accessible from project root

### Skill not appearing in autocomplete
- Verify SKILL.md has valid YAML frontmatter (3 dashes before/after)
- Check file is in `.claude/skills/<name>/SKILL.md`
- Restart Claude Code to reload skills

### MCP server not working
- Check `.mcp.json` syntax (valid JSON)
- Verify `npx` is available: `npx --version`
- Restart Claude Code after modifying `.mcp.json`
- Use `--mcp-debug` flag to see MCP logs

### Subagent not launching
- Verify agent file exists in `.claude/agents/`
- Check agent has valid markdown structure
- Use correct subagent_type in Task tool call
- Check agent has required tools listed
