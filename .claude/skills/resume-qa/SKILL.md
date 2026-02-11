---
name: resume-qa
description: Validate that generated resume content traces to source YAML blocks
disable-model-invocation: true
---

# Resume QA Validator

Validates generated resume content against constitutional constraints:
1. No hallucinated experience or metrics
2. All content traces to resume_blocks YAML
3. Adaptation only rewrites phrasing, never fabricates

## Usage
```
/resume-qa <output_file>
```

## Process
1. Read generated resume from `output/` directory
2. Extract all achievements, metrics, dates, and experience claims
3. Cross-reference against `data/resume_blocks/*.yaml` source files
4. Flag any content without source attribution
5. Report violations with line numbers and severity

## Constitutional Check

### ✅ PASS Criteria
- All experience has YAML source in resume_blocks
- Metrics match source data exactly or are derived logically
- Dates are accurate and traceable
- Skills claimed exist in skills.yaml
- Education matches education.yaml

### ❌ FAIL Criteria
- Fabricated achievements not in source YAML
- Inflated metrics beyond source data
- Companies or roles not in experience.yaml
- Technologies not in skills.yaml
- Dates that don't match source

## Output Format

```
Resume QA Report: output/resume_2024-01-15.pdf
==============================================

✅ CONSTITUTIONAL COMPLIANCE: PASS

Checked:
- 12 achievements (all traced to experience.yaml)
- 8 metrics (all match source data)
- 4 roles (all in experience.yaml)
- 15 skills (all in skills.yaml)

Warnings:
- Line 23: "Led team of 5" - source says "Led team of 3-5" (acceptable range)

No violations found.
```

## Implementation

1. Parse output file (PDF/DOCX/HTML)
2. Load all YAML files from data/resume_blocks/
3. Extract claims from resume
4. Cross-reference each claim
5. Generate detailed report
