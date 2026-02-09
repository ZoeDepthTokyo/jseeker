# PROTEUS v0.2 — UX Design Reference

## 1. Design Principles

### 1.1 Performance-First
- **Cache resume blocks**: Use `@st.cache_data` on YAML loading to prevent disk reads on every interaction
- **Cache DB connections**: Use `@st.cache_resource` for SQLite connections to prevent re-initialization
- **Session state for pipeline results**: Store `PipelineResult` in `st.session_state` after generation to avoid LLM re-calls on page interactions
- **Lazy-load previews**: Render resume PDFs/DOCX only on explicit user action, not on page load

### 1.2 Low Latency Perception
- **Use `st.status` for multi-step operations**: Shows progress steps during pipeline execution (parsing JD, matching, adapting, scoring, rendering)
- **Progress indicators during LLM calls**: Visual feedback for 3-5 second Claude API calls
- **Instant UI feedback**: `st.toast` for non-blocking confirmations (e.g., "Saved 3 changes"), `st.spinner` only for unavoidable blocking operations

### 1.3 Frictionless UX
- **One-click actions**: Primary user intent (Generate Resume, Import to Tracker) requires exactly 1 click
- **No confirmation dialogs for non-destructive actions**: Edit tracker inline, download files without prompts
- **Confirmations only for destructive actions**: Delete resume shows warning + confirm button (2-step)

### 1.4 Progressive Cognitive Load
- **Essential info first**: ATS score + export buttons always expanded, details collapsed by default
- **Collapsible sections**: JD Analysis, Template Match, Adaptation Details collapsed on load
- **Dashboard metrics at top**: 5 KPIs visible immediately (Total Apps, Active, This Week, Avg ATS, Monthly Cost)

### 1.5 Streamlit Constraints
- **No true SPA routing**: Use `st.switch_page()` for navigation, cannot preserve state across page switches
- **Top-to-bottom render model**: Components render sequentially, cannot update previous components without `st.rerun()`
- **Limited state management**: Session state persists within a session, cleared on browser refresh

## 2. Component Patterns

### 2.1 Progress Feedback
```python
with st.status("Generating resume...", expanded=True) as status:
    st.write("Parsing job description...")
    st.write("Adapting resume content...")
    status.update(label="Complete!", state="complete", expanded=False)
```
- Use for 5+ second operations
- Show step-by-step progress
- Collapse on completion

### 2.2 Progressive Disclosure
```python
with st.expander("JD Analysis", expanded=False):
    st.markdown(f"**Title:** {parsed_jd.title}")
```
- Essential info (ATS Score, Export): `expanded=True`
- Details (JD Analysis, Template Match): `expanded=False`

### 2.3 Inline Editing
```python
edited_df = st.data_editor(
    df,
    column_config={
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "application_status": st.column_config.SelectboxColumn(
            "App Status",
            options=[s.value for s in ApplicationStatus],
        ),
    },
    use_container_width=True,
    hide_index=True,
)
```
- Use for tracker table (3 status pipelines editable)
- Auto-save on detect changes via `df.equals(edited_df)`

### 2.4 Layout Patterns
```python
# Metrics row
col1, col2, col3, col4 = st.columns(4)
col1.metric("Label", "Value")

# Scrollable container
with st.container(height=500):
    st.dataframe(df)

# Side-by-side actions
col1, col2 = st.columns(2)
with col1:
    st.download_button("PDF", pdf_data)
with col2:
    st.download_button("DOCX", docx_data)
```

### 2.5 Non-Blocking Feedback
```python
st.toast("Saved 3 change(s)!")  # Disappears after 3s
st.success("Resume generated")   # Persistent success banner
st.warning("Approaching budget") # Persistent warning banner
```

## 3. Performance Rules

### 3.1 Caching
```python
@st.cache_data
def load_resume_blocks() -> list[dict]:
    """Cache YAML block loading — invalidates only on file change."""
    return yaml.safe_load(Path("blocks.yaml").read_text())

@st.cache_resource
def get_db_connection() -> sqlite3.Connection:
    """Cache DB connection — persists for session lifetime."""
    return sqlite3.connect("proteus.db")
```

### 3.2 Session State
```python
# Store pipeline result after generation
st.session_state["pipeline_result"] = run_pipeline(jd_text, jd_url)

# Reuse on page interactions (download, view details)
if "pipeline_result" in st.session_state:
    result = st.session_state["pipeline_result"]
```
- Never re-run `run_pipeline()` on button clicks for download/preview
- Clear on new JD input via `st.session_state.clear()`

### 3.3 Lazy Loading
- Resume previews: Render only when user clicks "View Resume"
- Job discovery results: Load on-demand via filters, not all at once
- Tracker table: Load only filtered applications (avoid loading all 1000+ rows)

## 4. Page-by-Page UX Specs

### 4.1 Dashboard
**Layout:**
- Metrics row (5 columns): Total Apps, Active, This Week, Avg ATS, Monthly Cost
- Recent Applications (expander, expanded by default): Last 10 apps, 3-column layout (company/role, status badges, actions)
- Quick Actions (3 buttons): New Resume, View Tracker, Discover Jobs

**Key UX:**
- Status badges use color + text (not color alone): "Resume: generated (blue)", "App: interview (green)"
- Click company/role row to view details (future: modal or detail page)

### 4.2 New Resume
**Flow:**
1. Budget display (3 metrics): Monthly Cost, Session Cost, Budget Remaining
2. JD input (textarea + URL input)
3. Generate button (primary, disabled if no JD or budget exceeded)
4. `st.status` progress (5 steps, collapses on completion)
5. Results:
   - **ATS Score Card** (expanded): Overall, Keyword Match, Recommended Format, Missing Keywords
   - **Export** (expanded): Editable filename, Download PDF/DOCX buttons
   - **JD Analysis** (collapsed): Parsed fields, keywords, pruned text
   - **Template Match** (collapsed): Relevance score, matched/missing keywords
   - **Adaptation Details** (collapsed): Summary, experience blocks with bullets
6. Cost display at bottom

**Key UX:**
- 1-click generation (no "are you sure?" prompt)
- Results stay on screen after generation (stored in session state)
- Budget warning at 80% (warning banner), hard stop at 100% (error + disabled button)

### 4.3 Resume Library
**Layout:**
- Table with version badges: ID, Company, Role, Version, ATS Score, Template, Created, Cost
- Per-resume actions: Download PDF, Download DOCX, Delete (with 2-step confirmation)

**Key UX:**
- Version badges auto-increment for same company + role
- Delete shows warning + confirm button (no accidental deletes)
- Table sortable by any column (Streamlit default)

### 4.4 Tracker
**Layout:**
- Sidebar filters: Application Status, Resume Status, Job Status (dropdowns)
- Inline-editable table (scrollable container, 500px height): 3 status pipelines (resume, application, job), notes, URL, location
- Auto-save on edit (no Save button)
- Import/Export section (collapsed expander): Export CSV, Import CSV
- Job Monitor section: "Check All Active Job URLs" button

**Key UX:**
- 3 status pipelines editable inline via dropdowns
- Changes save automatically on blur (shows toast "Saved 3 changes")
- No save button (reduces clicks, immediate feedback)

### 4.5 Job Discovery
**Layout:**
- Search Tags section: List of tags with Active/Inactive toggle buttons, "Add Tag" form
- Market selection: Multi-select (US, MX, default both)
- Search form: Location filter, job board multi-select (Indeed, LinkedIn, Wellfound), "Search Now" button
- Results table (sorted by posting date, newest first): Title, Company, Location, Posting Date, Source, Actions (Star, Dismiss, Import to Tracker, View Job)

**Key UX:**
- Search collects all active tags + markets + sources in 1 click
- Results deduped by URL (same job on multiple boards shown once)
- Import to Tracker creates application entry with URL, status defaults to "not_applied"

## 5. User Flows

### 5.1 Primary Flow (New Resume)
1. User navigates to "New Resume" page
2. User pastes JD text into textarea (optionally adds URL)
3. User clicks "Generate Resume" (1 click)
4. `st.status` shows 5-step progress (expands during, collapses on completion)
5. ATS Score Card appears (expanded by default)
6. User reviews score, missing keywords
7. User clicks "Download PDF" or "Download DOCX" (1 click per format)
8. Browser downloads file with editable filename

**Auto-tracker:**
- Pipeline creates application entry automatically with:
  - Company ID (looked up or created)
  - Role title, JD text, URL
  - Resume status: "exported"
  - Application status: "not_applied"
  - Job status: "active"

### 5.2 Version Management
- Same company + role = version increment (v1, v2, v3)
- All versions kept in library
- Resume Library table shows version badges
- Tracker links to latest version by default

### 5.3 Tracker Workflow
1. User navigates to "Tracker" page
2. Inline-editable table shows all applications
3. User changes application status from "not_applied" to "applied"
4. User changes resume status from "exported" to "submitted"
5. User adds notes: "Phone screen scheduled for 2026-02-10"
6. On blur, changes auto-save (toast: "Saved 3 changes")
7. User filters by status to view only "interview" stage apps

### 5.4 Job Discovery Workflow
1. User adds search tags: "Senior Product Designer", "Director of Design"
2. User selects markets: US, MX
3. User clicks "Search Now"
4. Spinner shows "Searching 2 tags across 3 boards in 2 markets"
5. Results appear sorted by posting date (newest first)
6. User clicks "Star" for interesting jobs
7. User clicks "Import to Tracker" for starred jobs
8. Application entry created with URL, JD text pre-filled (ready for resume generation)

## 6. Accessibility Notes

### 6.1 Color Usage
- **Never use color alone**: Status badges include text labels ("Active", "Rejected") alongside color
- **Contrast ratios**: Streamlit defaults meet WCAG 2.1 AA (4.5:1 for normal text)
- **Color-blind safe palette**: Blue (active), Gray (not started), Green (success), Red (rejected), Orange (ghosted)

### 6.2 Keyboard Navigation
- All interactive elements keyboard-navigable (Streamlit default)
- Tab order follows visual flow (top to bottom)
- Enter key submits forms, Space activates buttons

### 6.3 Text Size
- Rendered resume PDFs: Minimum 10pt body text (ATS-optimized)
- Streamlit UI: Standard sizes (16px body, 20px headings)
- Metric labels: 12px minimum

### 6.4 Screen Reader Support
- Metric labels read as "Total Applications: 42"
- Status badges read as "Resume Status: exported"
- Button labels descriptive: "Download PDF" (not "Download")

## 7. Streamlit-Specific Patterns

### 7.1 State Management
```python
# Initialize state on first load
if "pipeline_result" not in st.session_state:
    st.session_state["pipeline_result"] = None

# Clear state on new generation
if generate_button:
    st.session_state.clear()
```

### 7.2 Navigation
```python
if st.button("New Resume"):
    st.switch_page("pages/2_new_resume.py")
```
- Use for cross-page navigation
- Session state does NOT persist across pages
- Store persistent data in DB, not session state

### 7.3 Form Handling
```python
with st.form("add_tag"):
    new_tag = st.text_input("Tag")
    if st.form_submit_button("Add"):
        # Process tag
        st.rerun()  # Refresh UI after DB write
```
- Use forms for multi-field input (prevents partial submissions)
- Call `st.rerun()` after DB writes to reflect changes

### 7.4 Conditional Rendering
```python
if "pipeline_result" in st.session_state:
    result = st.session_state["pipeline_result"]
    with st.expander("ATS Score", expanded=True):
        st.metric("Score", result.ats_score.overall_score)
```
- Check session state before accessing
- Expandable sections prevent cluttered UI

## 8. Anti-Patterns (Avoid)

### 8.1 Multiple `st.rerun()` Calls
- Causes infinite render loops
- Use sparingly, only after DB writes or state changes

### 8.2 Heavy Computations Outside Caching
- YAML parsing, DB queries without `@st.cache_data` causes re-execution on every widget interaction

### 8.3 Nested Forms
- Streamlit does not support forms inside forms
- Use separate forms or single-field inputs outside forms

### 8.4 Relying on Page Order
- Users can navigate via sidebar directly to any page
- Each page must initialize its own state and DB connections

### 8.5 Long-Running Operations Without Feedback
- Always use `st.status` or `st.spinner` for >2 second operations
- Show progress steps for multi-phase operations (pipeline: 5 steps)

---

**Version:** v0.2.0
**Last Updated:** 2026-02-06
**Author:** GAIA UX/UI Design Lead
