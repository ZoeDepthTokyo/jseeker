"""PROTEUS Job Discovery — Tag-based job search across boards."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from proteus.tracker import tracker_db

st.title("Job Discovery")

# --- Search Tags Management ---
st.subheader("Search Tags")

tags = tracker_db.list_search_tags(active_only=False)

if tags:
    for tag in tags:
        col1, col2, col3 = st.columns([4, 1, 1])
        col1.text(tag["tag"])
        active = tag.get("active", True)
        col2.caption("Active" if active else "Inactive")
        if col3.button("Toggle", key=f"toggle_{tag['id']}"):
            tracker_db.toggle_search_tag(tag["id"], not active)
            st.rerun()
else:
    st.info("No search tags configured. Add some below.")

# Add new tag
with st.form("add_tag"):
    new_tag = st.text_input("New search tag", placeholder="e.g., Director of Product Design")
    if st.form_submit_button("Add Tag"):
        if new_tag.strip():
            result = tracker_db.add_search_tag(new_tag.strip())
            if result:
                st.success(f"Added tag: {new_tag}")
            else:
                st.warning("Tag already exists")
            st.rerun()

# --- Search ---
st.markdown("---")
st.subheader("Search Jobs")

location = st.text_input("Location filter", placeholder="e.g., San Francisco, Remote")

sources = st.multiselect(
    "Job boards to search",
    options=["indeed", "linkedin", "wellfound"],
    default=["indeed"],
)

if st.button("Search Now"):
    active_tags = tracker_db.list_search_tags(active_only=True)
    tag_strings = [t["tag"] for t in active_tags]

    if not tag_strings:
        st.error("No active search tags. Add some above.")
    else:
        with st.spinner(f"Searching {len(tag_strings)} tags across {len(sources)} boards..."):
            from proteus.job_discovery import search_jobs, save_discoveries
            discoveries = search_jobs(tag_strings, location=location, sources=sources)
            saved = save_discoveries(discoveries)

        st.success(f"Found {len(discoveries)} jobs, {saved} new (deduplicated)")

# --- Results ---
st.markdown("---")
st.subheader("Discovered Jobs")

status_filter = st.selectbox("Filter by status", options=["All", "new", "starred", "dismissed", "imported"])

if status_filter == "All":
    discoveries = tracker_db.list_discoveries()
else:
    discoveries = tracker_db.list_discoveries(status=status_filter)

if discoveries:
    for disc in discoveries:
        with st.container():
            col1, col2, col3 = st.columns([4, 2, 2])
            col1.markdown(f"**{disc['title']}** — {disc.get('company', '')}")
            col2.caption(disc.get("location", ""))
            col3.caption(f"Source: {disc.get('source', '')}")

            action_cols = st.columns(4)

            if disc.get("status") == "new":
                if action_cols[0].button("Star", key=f"star_{disc['id']}"):
                    tracker_db.update_discovery_status(disc["id"], "starred")
                    st.rerun()
                if action_cols[1].button("Dismiss", key=f"dismiss_{disc['id']}"):
                    tracker_db.update_discovery_status(disc["id"], "dismissed")
                    st.rerun()

            if disc.get("status") in ("new", "starred"):
                if action_cols[2].button("Import to Tracker", key=f"import_{disc['id']}"):
                    from proteus.job_discovery import import_discovery_to_application
                    app_id = import_discovery_to_application(disc["id"])
                    if app_id:
                        st.success(f"Imported as application #{app_id}")
                    else:
                        st.error("Failed to import")
                    st.rerun()

            if disc.get("url"):
                action_cols[3].markdown(f"[View Job]({disc['url']})")

            st.markdown("---")
else:
    st.info("No discovered jobs. Run a search above.")
