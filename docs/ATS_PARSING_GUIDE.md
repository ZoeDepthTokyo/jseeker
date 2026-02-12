# ATS Parsing Guide: Platform-Specific Requirements

**Last Updated**: February 12, 2026
**Version**: 1.0.0

## Executive Summary

Applicant Tracking Systems (ATS) parse resumes differently based on platform, file format, and layout. This guide documents formatting requirements for the six major ATS platforms jSeeker targets, ensuring maximum parseability and keyword matching.

## File Format Recommendations by Platform

| Platform | Preferred Format | Notes |
|----------|------------------|-------|
| **Greenhouse** | PDF | Modern parser handles PDFs perfectly, preserves formatting |
| **Workday** | PDF (default), DOCX (fallback) | AI-powered 2026 parser handles both, DOCX has highest parse rate historically |
| **Lever** | PDF | Modern parser, handles complex layouts well |
| **iCIMS** | PDF | Supports PDFs well, DOCX for older instances |
| **Ashby** | PDF | Modern platform, excellent PDF parsing |
| **Taleo** | DOCX | Older parser struggles with PDFs, prefers DOCX |

### General Rule
**Default to PDF** (preserves formatting, works with modern parsers). Switch to **DOCX only** when:
- Job posting explicitly requests DOCX
- Applying via Taleo or other legacy systems
- Parsing test fails with PDF

**Source**: [ResumeAdapter ATS Formatting Rules 2026](https://www.resumeadapter.com/blog/ats-resume-formatting-rules-2026), [Careery ATS Guide 2026](https://careery.pro/blog/resume-applications/how-to-get-resume-past-ats)

---

## Critical Formatting Rules (All Platforms)

### 1. Company Name and Job Title Separation ⚠️ **HIGH PRIORITY**

**REQUIRED**: Company name and job title MUST be on separate lines.

**Why**: Parsers use line breaks to distinguish fields. Single-line formats like "Software Engineer — Acme Corp" cause field misidentification.

**jSeeker Implementation** (✅ Compliant):
```python
# Role title (bold, separate paragraph)
role_para = doc.add_paragraph()
role_run = role_para.add_run(f"{exp['role']}")
role_run.bold = True

# Company name (separate paragraph, regular weight)
company_para = doc.add_paragraph()
company_run = company_para.add_run(f"{exp['company']}")
```

**Recommended Structure**:
```
Software Engineer                    # Line 1: Job Title (bold)
Acme Corporation                     # Line 2: Company Name
January 2022 – Present | Remote      # Line 3: Dates + Location
```

**Source**: [ATS Formatting Mistakes - Jobscan](https://www.jobscan.co/blog/ats-formatting-mistakes/), [ATS Resume Format 2026](https://www.intelligentcv.app/career/ats-resume-format-guide/)

---

### 2. Layout: Single-Column Only

**REQUIRED**: Use single-column layout. Avoid two-column designs, text boxes, or tables.

**Why**: Parsers read left-to-right, top-to-bottom. Multi-column layouts cause fields to be read out of order (e.g., all left column content, then all right column content).

**Example Failure**:
```
[Left Column]               [Right Column]
Software Engineer           January 2022 – Present
Acme Corp                   Remote
Led team of 5...

Parser reads: "Software Engineer Acme Corp Led team of 5... January 2022 – Present Remote"
```

**Source**: [How ATS Works in 2026](https://owlapply.com/en/blog/how-ats-works-in-2026-and-what-it-really-reads-on-your-resume), [CVCraft ATS Format 2026](https://cvcraft.roynex.com/blog/ats-resume-format-2026)

---

### 3. Standard Section Headers

**REQUIRED**: Use industry-standard section headers.

**Recognized Headers** (all platforms):
- ✅ Professional Experience / Work Experience / Experience
- ✅ Education
- ✅ Skills / Technical Skills
- ✅ Certifications
- ✅ Summary / Professional Summary

**Avoid Creative Headers**:
- ❌ "My Journey" → Parser thinks it's a biography, ignores keywords
- ❌ "What I've Built" → Not recognized as Experience section
- ❌ "Toolbox" → Not recognized as Skills section

**Why**: Parsers rely on header keywords to segment content. Custom headers break field mapping.

**Source**: [Do ATS Dream of Resume Formatting](https://theinterconnected.net/dafark8/do-ats-dream-of-resume-formatting/), [Santa Clara University ATS Guide](https://www.scu.edu/careercenter/toolkit/job-scan-common-ats-resume-formatting-mistakes/)

---

### 4. Date Formatting Consistency

**REQUIRED**: Use consistent date format throughout resume.

**Recommended Format**: `Month YYYY – Month YYYY` or `MM/YYYY – MM/YYYY`

**Examples**:
- ✅ January 2022 – December 2023
- ✅ 01/2022 – 12/2023
- ❌ Jan 2022 – December 2023 (inconsistent)
- ❌ 1/22 – 12/23 (ambiguous, parser fails)

**Why**: ATS calculates employment duration. Inconsistent formats cause miscalculation or field skip.

**Source**: [ATS Resume Formatting Rules 2026](https://www.resumeadapter.com/blog/ats-resume-formatting-rules-2026)

---

### 5. Fonts and Styling

**REQUIRED**: Use standard fonts. Avoid decorative fonts, images, graphics.

**Allowed Fonts**:
- Arial, Calibri, Garamond, Georgia, Helvetica, Times New Roman, Verdana

**Font Size**:
- Body text: 10-12pt
- Headers: 14-16pt
- Name: 16-18pt

**Styling**:
- ✅ Bold for emphasis (job titles, headers)
- ✅ Italic sparingly
- ❌ No colors (except dark gray/black for text)
- ❌ No text boxes, shapes, SmartArt
- ❌ No images, logos, photos
- ❌ No pie charts, infographics

**Why**: Images and graphics break OCR/parsing engines. Fancy fonts may not render correctly.

**Source**: [Workday ATS Guide 2025](https://www.atshiring.com/en/learn/workday-ats-guide-2025), [Teal HQ Workday Resume](https://www.tealhq.com/post/workday-resume)

---

### 6. No Scanned PDFs or Image-Based Files

**CRITICAL**: Only text-based PDFs are acceptable. Scanned images cannot be parsed.

**How to Verify**:
- Open PDF in browser
- Try to highlight/select text
- If text is selectable → Text-based PDF ✅
- If text is an image → Scanned PDF ❌

**Source**: [Lever ATS Guide](https://www.jobscan.co/blog/lever-ats/), [ATS Friendly Resume Guide 2026](https://owlapply.com/en/blog/ats-friendly-resume-guide-2026-format-keywords-score-and-fixes)

---

## Platform-Specific Parsing Details

### Workday

**Parsing Process**:
1. Converts PDF/DOCX to raw text
2. Identifies blocks using header keywords: "Contact", "Work", "Education"
3. Extracts fields: Job Title, Company, Start Date, End Date, Description

**Special Requirements**:
- Company name on separate line (not combined with title)
- Consistent date format (calculates tenure)
- Standard headers ("Professional Experience" not "My Jobs")

**Optimal Format**: DOCX has highest parse rate historically, but 2026 AI parser handles PDF well.

**Source**: [Workday ATS Guide 2025](https://www.atshiring.com/en/learn/workday-ats-guide-2025), [Resumly Workday Tailoring](https://www.resumly.ai/blog/how-to-tailor-resumes-for-workday-ats-specifically)

---

### Greenhouse

**Parsing Strengths**:
- Excellent PDF handling
- Tolerates two-column layouts (but single-column safer)
- Modern AI-powered parser

**Recommendations**:
- PDF recommended
- Single-column layout safest
- Standard fonts and headers

**Source**: [Greenhouse Support - Resumes](https://support.greenhouse.io/hc/en-us/sections/360000690451-Resumes), [Kudoswall ATS Score Guide](https://pro.kudoswall.com/guides/ats-resume-score-guide/)

---

### Lever

**Parsing Strengths**:
- Modern parser, handles PDFs well
- Good with standard layouts

**Weaknesses**:
- Struggles with images, graphics, non-standard characters
- May miss information in complex tables

**Recommendations**:
- PDF format
- Avoid tables for experience section
- Standard fonts only

**Source**: [Lever ATS Guide - Jobscan](https://www.jobscan.co/blog/lever-ats/)

---

### iCIMS

**Parsing Characteristics**:
- Supports PDF well for modern instances
- Older instances may prefer DOCX

**Weaknesses**:
- Struggles with images, graphics
- May not parse tables correctly

**Recommendations**:
- PDF for recent iCIMS versions
- DOCX for older instances (check posting)
- Avoid tables and graphics

**Source**: [ATS Resume Formatting Mistakes](https://www.jobscan.co/blog/ats-formatting-mistakes/)

---

### Ashby

**Parsing Strengths**:
- Modern platform (launched 2021)
- Excellent PDF parsing
- AI-powered keyword extraction

**Recommendations**:
- PDF strongly recommended
- Standard formatting best practices apply

---

### Taleo (Oracle)

**Parsing Weaknesses**:
- Oldest platform, legacy parser
- Struggles with PDFs
- Prefers DOCX

**Recommendations**:
- **Use DOCX for Taleo applications**
- Simplest possible formatting
- Avoid tables, graphics, columns entirely

**Source**: [Scale Jobs ATS Format 2026](https://scale.jobs/blog/ats-resume-format-2026-design-guide)

---

## jSeeker Implementation Checklist

### ✅ Compliant Features
- [x] Company name and job title on separate paragraphs (lines 403-417, renderer.py)
- [x] Single-column layout
- [x] Standard fonts (default: Arial/Calibri)
- [x] Standard section headers ("PROFESSIONAL EXPERIENCE", "SKILLS", "EDUCATION")
- [x] Consistent date format (Month YYYY – Month YYYY)
- [x] Text-based PDF generation (Playwright)
- [x] DOCX generation with proper paragraph structure (python-docx)
- [x] No images, tables, or graphics in experience section
- [x] Bold for job titles, regular weight for company names

### Platform-Aware Rendering
Current behavior: Always generates both PDF and DOCX.

**Recommendation for v0.4.0**: Add platform-aware format selection:
```python
def recommend_format(ats_platform: str) -> str:
    """Recommend file format based on ATS platform."""
    if ats_platform.lower() == "taleo":
        return "docx"
    elif ats_platform.lower() in ["greenhouse", "workday", "lever", "icims", "ashby"]:
        return "pdf"
    else:
        return "both"  # Generate both, let user choose
```

---

## Testing ATS Parseability

### Manual Tests
1. **Text Selection Test** (PDF): Open in browser, verify text is selectable
2. **Parse Test**: Upload to [Jobscan](https://www.jobscan.co/) or [ATSFriendly.com](https://www.atsfriendly.com/)
3. **Visual Inspection**: Verify company/title on separate lines, no merged fields

### Automated Tests (See test_renderer.py)
```python
def test_docx_structure_company_title_separation():
    """Verify company and title are separate paragraphs."""
    # Generate DOCX
    # Parse with python-docx
    # Assert: exp_block index n = title (bold), index n+1 = company (not bold)
```

---

## Common Parsing Failures

| Issue | Cause | Fix |
|-------|-------|-----|
| Company name missing | Combined with title on one line | Separate paragraphs |
| Experience dates missing | Inconsistent format (Jan 22 vs 01/2022) | Standardize date format |
| Skills section ignored | Creative header ("Toolbox") | Use "SKILLS" or "TECHNICAL SKILLS" |
| Text garbled | Scanned PDF or image | Use text-based PDF/DOCX |
| Fields read out of order | Two-column layout | Use single-column layout |
| Job title not bold | No styling | Apply bold to title runs |

---

## References

### Primary Sources
- [How to Get Your Resume Past ATS in 2026 - Careery](https://careery.pro/blog/resume-applications/how-to-get-resume-past-ats)
- [ATS Resume Formatting Rules 2026 - ResumeAdapter](https://www.resumeadapter.com/blog/ats-resume-formatting-rules-2026)
- [How ATS Works in 2026 - OwlApply](https://owlapply.com/en/blog/how-ats-works-in-2026-and-what-it-really-reads-on-your-resume)
- [ATS Resume Format 2026 - Scale Jobs](https://scale.jobs/blog/ats-resume-format-2026-design-guide)
- [Workday ATS Guide 2025 - ATS Hiring Platform](https://www.atshiring.com/en/learn/workday-ats-guide-2025)

### Platform-Specific
- [Workday Resume Format - Teal HQ](https://www.tealhq.com/post/workday-resume)
- [Lever ATS Guide - Jobscan](https://www.jobscan.co/blog/lever-ats/)
- [Greenhouse Support - Resumes](https://support.greenhouse.io/hc/en-us/sections/360000690451-Resumes)
- [Free ATS Resume Score Guide - Kudoswall](https://pro.kudoswall.com/guides/ats-resume-score-guide/)

### Formatting Best Practices
- [ATS Formatting Mistakes - Jobscan](https://www.jobscan.co/blog/ats-formatting-mistakes/)
- [ATS Resume Format 2026 - CVCraft](https://cvcraft.roynex.com/blog/ats-resume-format-2026)
- [ATS-Friendly Resume Guide 2026 - OwlApply](https://owlapply.com/en/blog/ats-friendly-resume-guide-2026-format-keywords-score-and-fixes)
- [Do ATS Dream of Resume Formatting? - The Interconnected](https://theinterconnected.net/dafark8/do-ats-dream-of-resume-formatting/)

---

## Changelog

**v1.0.0** (2026-02-12)
- Initial documentation
- Verified jSeeker compliance with all major ATS platforms
- Documented platform-specific parsing requirements
- Added testing recommendations
