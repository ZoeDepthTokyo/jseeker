# jSeeker v0.3.0 Manual Testing Guide

## Overview
This guide provides comprehensive manual test scenarios to verify all 21 issues from Phase 1-2 feedback are resolved and features work correctly.

**Test Environment:**
- jSeeker v0.3.0
- Python 3.14+
- Anthropic API key configured in `.env`
- Database: `data/jseeker.db`

---

## Pre-Test Setup

### 1. Environment Check
```bash
# Verify Python version
python --version  # Should be 3.14+

# Activate virtual environment
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Mac/Linux

# Verify dependencies
pip list | grep -E "anthropic|streamlit|playwright"

# Check .env configuration
cat .env | grep ANTHROPIC_API_KEY  # Should not be empty
```

### 2. Start Application
```bash
# Option 1: Full pipeline (recommended for testing)
python run.py

# Option 2: jSeeker only
streamlit run ui/app.py --server.port 8502

# Access at: http://localhost:8502
```

### 3. Clear Cache (if needed)
```bash
# Clear Streamlit cache
rm -rf .streamlit/cache

# Clear Python bytecode
find . -name "__pycache__" -type d -exec rm -rf {} +
```

---

## Test Scenario 1: Batch Resume Generation

**Issues Tested:** #1, #2, #3, #7, #17, #18, #19, #20, #21
**Phase:** 1 (Agent 1)
**Expected Duration:** 5-10 minutes

### 1.1 Batch URL Submission

**Steps:**
1. Navigate to **Dashboard** page
2. Locate **Batch Generate from URLs** section
3. Paste the following test URLs (one per line):
   ```
   https://careers.google.com/jobs/results/123456789/
   https://www.linkedin.com/jobs/view/3456789012
   https://greenhouse.io/test-company/jobs/1234567
   https://lever.co/test-company/job-12345
   https://workday.com/test-company/job/JR12345
   ```
4. Click **Start Batch Generation**

**Expected Results:**
- ✅ Batch job created with unique ID
- ✅ Progress bar appears showing "0/5 jobs"
- ✅ **Pause**, **Resume**, **Stop** buttons visible
- ✅ Worker status panel shows 5 workers (or max_workers setting)
- ✅ No errors in UI

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 1.2 Parallel Processing

**Steps:**
1. Observe worker status panel during batch processing
2. Check progress bar updates
3. Monitor job completion rate

**Expected Results:**
- ✅ Multiple jobs process simultaneously (5 workers active)
- ✅ Progress updates in real-time (every 2 seconds)
- ✅ Estimated completion time displayed
- ✅ Jobs complete faster than sequential (< 2 min total for 5 URLs)

**Pass/Fail:** ________

**Observed Processing Time:** ________

**Notes:**
_________________________________________________________________


### 1.3 Pause/Resume Controls

**Steps:**
1. Start batch job with 10 URLs
2. Wait until 3-4 jobs complete
3. Click **Pause** button
4. Wait 10 seconds
5. Click **Resume** button
6. Wait for all jobs to complete

**Expected Results:**
- ✅ Pause: Running jobs finish, no new jobs start
- ✅ Pause: Progress bar shows "Paused" indicator
- ✅ Pause: Worker status shows "Idle" or "Completing current job"
- ✅ Resume: Processing continues from paused state
- ✅ Resume: Remaining jobs complete successfully
- ✅ No data loss or corruption

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 1.4 Stop Functionality

**Steps:**
1. Start batch job with 10 URLs
2. Wait until 2-3 jobs complete
3. Click **Stop** button
4. Check final state

**Expected Results:**
- ✅ All workers stop gracefully
- ✅ Completed jobs saved to database
- ✅ Incomplete jobs marked as "Stopped" or "Pending"
- ✅ Batch progress shows partial completion (e.g., "3/10 completed")
- ✅ No hanging processes

**Pass/Fail:** ________

**Completed Jobs:** ________ / ________

**Notes:**
_________________________________________________________________


### 1.5 Error Handling

**Steps:**
1. Submit batch with invalid URLs:
   ```
   https://invalid-domain-12345.com/job
   https://careers.google.com/404-not-found
   not-a-url-at-all
   ```
2. Monitor error handling

**Expected Results:**
- ✅ Failed jobs show in "Failed" count
- ✅ Error messages logged to console (DEBUG level)
- ✅ Other valid jobs continue processing
- ✅ No application crash
- ✅ Failed jobs list shows reason (e.g., "Could not extract job description")

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 1.6 Skip Known URLs

**Steps:**
1. Submit batch with 3 URLs
2. Wait for completion
3. Submit same batch again

**Expected Results:**
- ✅ Second batch skips all 3 URLs (already in database)
- ✅ Skipped jobs show in "Skipped" count
- ✅ Message: "URL already exists in tracker"
- ✅ Batch completes instantly
- ✅ No duplicate applications created

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


---

## Test Scenario 2: PDF Formatting

**Issues Tested:** #8, #9, #10
**Phase:** 1 (Agent 2)
**Expected Duration:** 10-15 minutes

### 2.1 Single Font Family

**Steps:**
1. Navigate to **New Resume** page
2. Paste a test JD (English or Spanish)
3. Generate resume
4. Download PDF
5. Open PDF in Adobe Acrobat or similar
6. Use **File > Properties > Fonts** to inspect fonts

**Expected Results:**
- ✅ Only ONE font family used throughout document
- ✅ No Calibri font present
- ✅ System font stack: -apple-system, BlinkMacSystemFont, Segoe UI, Arial
- ✅ Consistent font rendering on all pages

**Pass/Fail:** ________

**Fonts Found:** ________________________

**Notes:**
_________________________________________________________________


### 2.2 Typography Hierarchy

**Steps:**
1. Open generated PDF
2. Inspect visual hierarchy:
   - **Name (h1):** Should be 22pt, bold
   - **Title (h2):** Should be 13pt, italic
   - **Section headers (h3):** Should be 11pt, bold, 2px border
   - **Body text:** Should be 10pt, regular
   - **Company names:** Should be italic
   - **Achievements:** Should use bold for metrics/impact

**Expected Results:**
- ✅ Name (h1) = 22pt, bold
- ✅ Title (h2) = 13pt, italic
- ✅ Section h3 = 11pt, bold, 2px solid border
- ✅ Body = 10pt, regular
- ✅ Company names = italic
- ✅ Metrics/impact = bold (font-weight: 700, color: #1a1a1a)

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 2.3 Spacing & Layout

**Steps:**
1. Inspect PDF spacing:
   - Line height
   - Section margins
   - Bullet point spacing
   - Experience entry spacing

**Expected Results:**
- ✅ Body line-height = 1.4
- ✅ Section h3 margin-bottom = 16pt
- ✅ Bullet li margin-bottom = 3pt
- ✅ Experience entry margin-bottom = 16pt
- ✅ No overlapping text
- ✅ Consistent whitespace

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 2.4 Information Order (ATS Compliance)

**Steps:**
1. Open PDF
2. Verify section order in right column:
   - Header (name, title, contact)
   - Summary
   - Experience (most recent first)
3. Verify left column:
   - Education
   - Skills
   - Certifications (if any)

**Expected Results:**
- ✅ Right column: Header → Summary → Experience
- ✅ Experience entries in reverse chronological order
- ✅ Left column: Education → Skills → Certifications
- ✅ Most important content (Experience) appears first for ATS parsing

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 2.5 Language-Based Address Routing

**Steps:**
1. **Test English JD:**
   - Paste JD in English (US-based job)
   - Generate resume
   - Check address in PDF header
   - **Expected:** "San Diego, CA, USA"

2. **Test Spanish JD:**
   - Paste JD in Spanish (Mexico-based job)
   - Generate resume
   - Check address in PDF header
   - **Expected:** "Ciudad de México, CDMX, México"

3. **Test French JD:**
   - Paste JD in French (France-based job)
   - Generate resume
   - Check address in PDF header
   - **Expected:** "San Diego, CA, USA" (default fallback)

**Expected Results:**
- ✅ English JD → San Diego, CA, USA
- ✅ Spanish JD → Ciudad de México, CDMX, México
- ✅ French/Other → San Diego, CA, USA (default)
- ✅ Address routing automatic (no manual selection)

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


---

## Test Scenario 3: Job Discovery

**Issues Tested:** #4, #5, #6, #22, #23
**Phase:** 1 (Agent 3)
**Expected Duration:** 15-20 minutes

### 3.1 Search Tag Weights

**Steps:**
1. Navigate to **Job Discovery** page
2. In **Manage Search Tags** section:
   - Add "Director of Product" with weight **80**
   - Add "Product Manager" with weight **60**
   - Add "UX Designer" with weight **30**
3. Click **Save Weights**
4. Run search

**Expected Results:**
- ✅ Tags saved with correct weights
- ✅ Search results ranked by tag weight (Director listings first)
- ✅ Weight displayed in tag chips
- ✅ Weights editable after save
- ✅ Weights persist across page refreshes

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 3.2 Market & Location Filters

**Steps:**
1. Select markets:
   - ✅ United States (US)
   - ✅ Mexico (MX)
   - ✅ Canada (CA)
2. Leave **Location** filter empty (use market defaults)
3. Run search
4. Verify default locations used:
   - US → "Remote"
   - MX → "Ciudad de México"
   - CA → "Toronto"

**Expected Results:**
- ✅ Each market uses correct default location
- ✅ No "unclear relation between Markets and Location" error
- ✅ Results returned from all 3 markets
- ✅ Market field stored separately from source

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 3.3 250-Job Pause Limit

**Steps:**
1. Configure search to find many results:
   - Tags: "Product Manager", "UX Designer", "Software Engineer"
   - Markets: US, UK, Germany (3 markets × 3 sources = 9 searches)
2. Run search
3. Monitor job count

**Expected Results:**
- ✅ Search pauses automatically at 250 discoveries
- ✅ Message: "Limit reached: 250 jobs discovered"
- ✅ **Resume Search** button appears
- ✅ Pause occurs gracefully (current page finishes)
- ✅ No crash or memory issues

**Pass/Fail:** ________

**Final Job Count:** ________

**Notes:**
_________________________________________________________________


### 3.4 Source & Market Separation

**Steps:**
1. Run search for US, MX, CA markets
2. Navigate to **Discovered Jobs** page
3. Check job entries in table

**Expected Results:**
- ✅ **Source** column shows: "linkedin", "indeed", "wellfound" (no suffix)
- ✅ **Market** column shows: "us", "mx", "ca"
- ✅ No entries like "linkedin_mx" or "indeed_us" in source field
- ✅ Clean data architecture

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 3.5 Jobs Grouped by Location

**Steps:**
1. Navigate to **Discovered Jobs** page
2. Check grouping/display

**Expected Results:**
- ✅ Jobs grouped by **Location** (e.g., "Remote", "San Francisco", "Toronto")
- ✅ Each group has expandable section
- ✅ Job count per location visible
- ✅ No "Uncategorized 1066 jobs" issue
- ✅ Easy to navigate large result sets

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


---

## Test Scenario 4: Application Tracker

**Issues Tested:** #11, #12, #13
**Phase:** 2 (Agent 4)
**Expected Duration:** 10 minutes

### 4.1 Role & URL Column Merge

**Steps:**
1. Navigate to **Application Tracker** page
2. View applications table

**Expected Results:**
- ✅ **Role** column displays job title as clickable link
- ✅ Clicking role opens URL in new tab
- ✅ URL column removed (merged into role)
- ✅ Cleaner, more compact table layout
- ✅ Links work correctly

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 4.2 Salary Information Display

**Steps:**
1. In Application Tracker table, check **Salary** column
2. Verify display format:
   - With salary: "$120,000 - $150,000 USD"
   - Without salary: "Not specified"

**Expected Results:**
- ✅ Salary column present
- ✅ Format: "$[min] - $[max] [currency]"
- ✅ Empty cells show "Not specified"
- ✅ Currency options: USD, EUR, GBP, MXN

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 4.3 Relevance Score Tooltip

**Steps:**
1. Hover over **Relevance** column values
2. Read tooltip explanation

**Expected Results:**
- ✅ Tooltip appears on hover
- ✅ Explains relevance categories:
  - 0-25%: Low match
  - 26-50%: Medium match
  - 51-75%: Good match
  - 76-100%: Excellent match
- ✅ Tooltip mentions: "Match between your experience and job requirements"
- ✅ Color coding matches category (red/yellow/green)

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


---

## Test Scenario 5: Resume Library

**Issues Tested:** #14, #15, #16
**Phase:** 2 (Agent 5)
**Expected Duration:** 10 minutes

### 5.1 PDF Template Upload

**Steps:**
1. Navigate to **Resume Library** page
2. In **Upload PDF Templates** section:
   - Upload 2 PDF files:
     - English resume template
     - Spanish resume template
   - Set **Template Name** for each
   - Select **Language** for each
3. Click **Upload**

**Expected Results:**
- ✅ Both PDFs uploaded successfully
- ✅ Saved to `docs/Resume References/`
- ✅ Metadata saved to `data/resume_sources.json`
- ✅ File size displayed (KB)
- ✅ Upload timestamp recorded
- ✅ Success message shown

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 5.2 Template Display & Preview

**Steps:**
1. View **Uploaded Templates** section
2. Check template cards

**Expected Results:**
- ✅ Each template shows:
  - Template name
  - Language
  - File size
  - Upload date
- ✅ **Preview** button visible
- ✅ **Delete** button visible
- ✅ Template cards styled consistently

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 5.3 PDF Preview Rendering

**Steps:**
1. Click **Preview** on uploaded template
2. View rendered preview

**Expected Results:**
- ✅ PDF renders as image (PNG)
- ✅ First page displayed
- ✅ Readable quality (150 DPI)
- ✅ Fallback message if PyMuPDF unavailable
- ✅ No crashes or errors

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 5.4 Template Deletion

**Steps:**
1. Click **Delete** on a template
2. Confirm deletion

**Expected Results:**
- ✅ Template removed from UI
- ✅ PDF file deleted from `docs/Resume References/`
- ✅ Metadata removed from `resume_sources.json`
- ✅ Confirmation prompt before delete
- ✅ No orphaned files or metadata

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


---

## Test Scenario 6: Learning System Transparency

**Issues Tested:** #24, #25, #26
**Phase:** 2 (Agent 6)
**Expected Duration:** 10 minutes

### 6.1 Pattern Statistics Display

**Steps:**
1. Navigate to **Analytics** page
2. View **Pattern Learning Stats** section

**Expected Results:**
- ✅ Total patterns learned displayed
- ✅ Pattern cache hit rate shown (%)
- ✅ Cost saved from pattern reuse (USD)
- ✅ Total pattern uses
- ✅ Top 10 patterns table
- ✅ Breakdown by pattern type

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 6.2 ATS Score Explanations

**Steps:**
1. Navigate to **New Resume** page
2. Generate a resume
3. View **ATS Analysis** section after generation
4. Read score explanation

**Expected Results:**
- ✅ **Original Score** displayed (e.g., "72/100")
- ✅ **Improved Score** displayed (e.g., "89/100")
- ✅ **Chain-of-thought explanation**:
  - Why original score was low
  - What improvements were made
  - Why new score is higher
- ✅ Explanation in natural language
- ✅ Verifiable, non-technical reasoning

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 6.3 Cost Tracking Display

**Steps:**
1. Navigate to **Analytics** page
2. View **API Cost Tracking** section

**Expected Results:**
- ✅ Total cost (USD) displayed
- ✅ Cost by model (Haiku vs Sonnet)
- ✅ Cost by task (JD parse, adaptation, etc.)
- ✅ Token usage displayed (input/output/cached)
- ✅ Cost savings from caching shown
- ✅ Date range filter available

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


### 6.4 Learning System Feedback Loop

**Steps:**
1. Generate resume
2. Edit resume in **Resume Editor**
3. Save edits
4. Check if system learned from edit

**Expected Results:**
- ✅ Edit captured as user feedback
- ✅ Pattern learner extracts adaptation rule
- ✅ Future resumes apply learned pattern
- ✅ Pattern confidence increases with reuse
- ✅ Cost savings accumulate over time

**Pass/Fail:** ________

**Notes:**
_________________________________________________________________


---

## Post-Test Verification

### Database Integrity Check
```bash
# Connect to database
sqlite3 data/jseeker.db

# Check table counts
SELECT COUNT(*) FROM applications;
SELECT COUNT(*) FROM resumes;
SELECT COUNT(*) FROM job_discoveries;
SELECT COUNT(*) FROM learned_patterns;
SELECT COUNT(*) FROM api_costs;

# Verify no orphaned records
SELECT COUNT(*) FROM resumes WHERE application_id NOT IN (SELECT id FROM applications);

# Exit
.exit
```

**Expected Results:**
- ✅ All tables have data
- ✅ No orphaned records
- ✅ No NULL foreign keys

**Pass/Fail:** ________


### Log File Check
```bash
# Check for errors in logs
grep -i "error" logs/*.log | grep -v "DEBUG"
grep -i "exception" logs/*.log
```

**Expected Results:**
- ✅ No unhandled exceptions
- ✅ No authentication errors (401)
- ✅ No critical failures

**Pass/Fail:** ________


---

## Issue Resolution Checklist

Verify all 21 issues are resolved:

### Phase 1 - Batch Processing (Agent 1)
- [ ] #1: Batch tool has pause/stop/start buttons
- [ ] #2: Parallel processing (5 agents max)
- [ ] #3: Batch generation works end-to-end
- [ ] #7: Performance optimized (local library research)

### Phase 1 - PDF Formatting (Agent 2)
- [ ] #8: Single font family (no Calibri, no font mixing)
- [ ] #9: Proper spacing, hierarchy, bold/italic usage
- [ ] #10: Information order ATS-compliant

### Phase 1 - Job Discovery (Agent 3)
- [ ] #4: Market/location relationship clear
- [ ] #5: Tag weights implemented (priority ranking)
- [ ] #6: 250-job pause limit

### Phase 2 - Application Tracker (Agent 4)
- [ ] #11: Role & URL columns merged
- [ ] #12: Salary info in tracker chart
- [ ] #13: Relevance column tooltip/explanation

### Phase 2 - Resume Library (Agent 5)
- [ ] #14: PDF upload UI (English template)
- [ ] #15: PDF upload UI (Spanish template)
- [ ] #16: Template preview rendering

### Phase 2 - Learning System (Agent 6)
- [ ] #17: Single JD URL capture works
- [ ] #18: JD pruning removes non-relevant info
- [ ] #19: Pattern learning visible (stats dashboard)
- [ ] #20: Cost tracking visible (analytics page)
- [ ] #21: ATS score explanation (chain-of-thought)

### Cross-Cutting
- [ ] #22: Job discovery filters work correctly
- [ ] #23: Job discovery grouping by location


---

## Summary

**Total Test Scenarios:** 6
**Total Test Cases:** 30+
**Expected Testing Time:** 60-90 minutes

**Tester Name:** ______________________
**Test Date:** ______________________
**jSeeker Version:** 0.3.0
**Test Environment:** ______________________

**Overall Pass/Fail:** ________

**Critical Issues Found:** ____________________________________
_________________________________________________________________
_________________________________________________________________

**Recommendations for v0.3.1:** _______________________________
_________________________________________________________________
_________________________________________________________________
