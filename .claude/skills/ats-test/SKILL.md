---
name: ats-test
description: Quick ATS compliance scoring for a resume file
disable-model-invocation: true
---

# ATS Quick Test

Runs ATS scoring for all 6 supported platforms without launching the full UI wizard.

## Supported Platforms
- Greenhouse
- Workday
- Lever
- iCIMS
- Ashby
- Taleo

## Usage

```
# Score against all platforms
/ats-test output/resume_latest.pdf

# Score against specific platform
/ats-test output/resume_latest.pdf --platform greenhouse

# Score with detailed report
/ats-test output/resume_latest.pdf --verbose
```

## Output Format

```
ATS Compliance Report
=====================

File: output/resume_2024-01-15.pdf
Generated: 2024-01-15 10:30:00

Platform Scores:
┌─────────────┬───────┬──────────────┬─────────────────┐
│ Platform    │ Score │ Keyword Rate │ Status          │
├─────────────┼───────┼──────────────┼─────────────────┤
│ Greenhouse  │  87%  │    92%       │ ✅ Excellent    │
│ Workday     │  82%  │    88%       │ ✅ Good         │
│ Lever       │  79%  │    85%       │ ⚠️  Acceptable  │
│ iCIMS       │  91%  │    95%       │ ✅ Excellent    │
│ Ashby       │  85%  │    90%       │ ✅ Good         │
│ Taleo       │  76%  │    82%       │ ⚠️  Acceptable  │
└─────────────┴───────┴──────────────┴─────────────────┘

Overall: 83% (Good)

Critical Issues:
- Missing keywords: "Python", "AWS", "Docker" (for Taleo)
- Formatting: Bullet points not recognized by Lever parser

Recommendations:
1. Add Python version specifics (e.g., "Python 3.11")
2. Use standard bullet points (•) instead of dashes (-)
3. Add section header "Technical Skills" for better parsing
```

## Implementation

Uses `jseeker.ats_scorer` module:
1. Load resume file from output/
2. Extract text content
3. Load platform profiles from data/ats_profiles/
4. Score against each platform
5. Generate comparison report

## Options

- `--platform <name>`: Score against single platform only
- `--verbose`: Include detailed keyword analysis
- `--json`: Output in JSON format for automation
- `--threshold <score>`: Set minimum acceptable score (default: 75)

## Exit Codes

- 0: All platforms meet threshold
- 1: One or more platforms below threshold
- 2: Error processing file
