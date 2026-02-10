"""JSEEKER Job Discovery - Tag-based job search across boards."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from jseeker.tracker import tracker_db


st.title("Job Discovery")

# --- Search Tags Management ---
with st.expander("Search Tags", expanded=False):
    tags = tracker_db.list_search_tags(active_only=False)

    if tags:
        for tag in tags:
            col1, col2, col3 = st.columns([4, 1, 1])
            col1.text(tag["tag"])
            active = bool(tag.get("active", True))
            col2.caption("Active" if active else "Inactive")
            if col3.button("Toggle", key=f"toggle_{tag['id']}"):
                tracker_db.toggle_search_tag(tag["id"], not active)
                st.rerun()
    else:
        st.info("No search tags configured. Add some below.")

    with st.form("add_tag"):
        new_tag = st.text_input("New search tag", placeholder="e.g., Director of Product Design")
        submitted = st.form_submit_button("Add Tag")
        if submitted:
            if new_tag.strip():
                result = tracker_db.add_search_tag(new_tag.strip())
                if result:
                    st.success(f"Added tag: {new_tag.strip()}")
                else:
                    st.warning("Tag already exists or was empty.")
                st.rerun()

# --- Market Selection ---
st.markdown("---")
st.subheader("Markets")

from jseeker.job_discovery import MARKET_CONFIG

market_options = {code: config["name"] for code, config in MARKET_CONFIG.items()}
if "job_discovery_markets" not in st.session_state:
    st.session_state["job_discovery_markets"] = ["us", "mx"]

selected_markets = st.multiselect(
    "Active markets",
    options=list(market_options.keys()),
    default=st.session_state["job_discovery_markets"],
    format_func=lambda x: market_options[x],
    key="job_discovery_markets_widget",
)
st.session_state["job_discovery_markets"] = selected_markets

# --- Search ---
st.markdown("---")
st.subheader("Search Jobs")

location = st.text_input("Location filter", placeholder="e.g., San Francisco, Remote")

sources = st.multiselect(
    "Job boards to search",
    options=["indeed", "linkedin", "wellfound"],
    default=["indeed"],
)
st.caption("Note: Web scraping results vary. If no results appear, try different tags or check the Search Details after running.")

if "linkedin" in sources:
    st.info(
        "LinkedIn may return limited results due to anti-bot protections. "
        "Indeed usually returns more consistent results."
    )

if st.button("Search Now"):
    active_tags = tracker_db.list_search_tags(active_only=True)
    tag_strings = [t["tag"] for t in active_tags]

    if not tag_strings:
        st.error("No active search tags. Add and activate tags first.")
    elif not selected_markets:
        st.error("Select at least one market to search.")
    else:
        with st.spinner(
            f"Searching {len(tag_strings)} tag(s) across {len(sources)} board(s) in {len(selected_markets)} market(s)..."
        ):
            from jseeker.job_discovery import save_discoveries, search_jobs

            discoveries = search_jobs(
                tag_strings,
                location=location,
                sources=sources,
                markets=selected_markets,
            )
            saved = save_discoveries(discoveries)

        st.success(f"Found {len(discoveries)} jobs, {saved} new (deduplicated)")

        # Show search diagnostics
        with st.expander("Search Details", expanded=False):
            st.caption(f"Searched {len(tag_strings)} tag(s) x {len(sources)} source(s) x {len(selected_markets)} market(s)")
            st.caption(f"= {len(tag_strings) * len(sources) * len(selected_markets)} search combinations")
            st.caption(f"Total results before dedup: {len(discoveries)}")
            st.caption(f"New results saved: {saved}")

# --- Results ---
st.markdown("---")
st.subheader("Discovered Jobs")

status_filter = st.selectbox(
    "Filter by status",
    options=["All", "new", "starred", "dismissed", "imported"],
)
search_query = st.text_input(
    "Search discovered jobs",
    placeholder="Title, company, location, source, or tag",
)

status_value = None if status_filter == "All" else status_filter
discoveries = tracker_db.list_discoveries(status=status_value, search=search_query)

if discoveries:
    discoveries.sort(
        key=lambda d: (d.get("posting_date") or "", d.get("discovered_at") or ""),
        reverse=True,
    )

if discoveries:
    # Group discoveries by market
    from collections import defaultdict
    by_market = defaultdict(list)
    for d in discoveries:
        by_market[d.get("market", "unknown")].append(d)

    # Market display names
    MARKET_NAMES = {
        "us": "United States",
        "mx": "Mexico",
        "ca": "Canada",
        "uk": "United Kingdom",
        "es": "Spain",
        "dk": "Denmark",
        "fr": "France",
    }

    # Display each market group
    for market_code in sorted(by_market.keys()):
        market_name = MARKET_NAMES.get(market_code, market_code.upper())
        market_jobs = by_market[market_code]

        with st.expander(f"{market_name} ({len(market_jobs)} jobs)", expanded=True):
            for disc in market_jobs:
                with st.container():
                    col1, col2, col3 = st.columns([4, 2, 2])
                    col1.markdown(f"**{disc['title']}** - {disc.get('company', '')}")
                    col2.caption(disc.get("location", ""))
                    posting_date = disc.get("posting_date", "")
                    source = disc.get("source", "")
                    status = str(disc.get("status", "new")).strip().lower()
                    col3.caption(f"{posting_date} | {source} | {status}")

                    action_cols = st.columns(4)

                    if status == "new":
                        if action_cols[0].button("Star", key=f"star_{disc['id']}"):
                            tracker_db.update_discovery_status(disc["id"], "starred")
                            st.rerun()
                        if action_cols[1].button("Dismiss", key=f"dismiss_{disc['id']}"):
                            tracker_db.update_discovery_status(disc["id"], "dismissed")
                            st.rerun()

                    if status in ("new", "starred"):
                        if action_cols[2].button("Import to Tracker", key=f"import_{disc['id']}"):
                            from jseeker.job_discovery import import_discovery_to_application

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
    st.info("No discovered jobs match your current filters. Run a search above.")
