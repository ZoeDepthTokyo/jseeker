"""JSEEKER Job Discovery - Tag-based job search across boards."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from jseeker.tracker import tracker_db


st.title("Job Discovery")

# --- Saved Searches Sidebar ---
with st.sidebar:
    st.subheader("Saved Searches")

    saved_searches = tracker_db.list_saved_searches()

    if saved_searches:
        # Display saved searches
        for search in saved_searches:
            with st.expander(f"📌 {search['name']}", expanded=False):
                st.caption(f"Tags: {', '.join(search['tag_weights'].keys())}")
                if search.get('markets'):
                    st.caption(f"Markets: {', '.join(search['markets'])}")
                if search.get('sources'):
                    st.caption(f"Sources: {', '.join(search['sources'])}")
                if search.get('location'):
                    st.caption(f"Location: {search['location']}")

                col1, col2 = st.columns(2)

                # Load button
                if col1.button("Load", key=f"load_{search['id']}"):
                    # Load tag weights
                    for tag, weight in search['tag_weights'].items():
                        tracker_db.set_tag_weight(tag, weight)

                    # Load markets
                    if search.get('markets'):
                        st.session_state["job_discovery_markets"] = search['markets']

                    # Store sources and location in session for later UI sync
                    if search.get('sources'):
                        st.session_state["loaded_sources"] = search['sources']
                    if search.get('location'):
                        st.session_state["loaded_location"] = search['location']

                    st.success(f"Loaded: {search['name']}")
                    st.rerun()

                # Delete button
                if col2.button("Delete", key=f"delete_{search['id']}"):
                    if tracker_db.delete_saved_search(search['id']):
                        st.success(f"Deleted: {search['name']}")
                        st.rerun()
                    else:
                        st.error("Failed to delete")
    else:
        st.info("No saved searches yet. Configure a search below and save it.")

    # Save current search form
    with st.form("save_search_form"):
        st.markdown("---")
        st.caption("Save Current Configuration")
        search_name = st.text_input("Search name", placeholder="e.g., Senior PM - Remote US")
        save_button = st.form_submit_button("Save Current Search")

        if save_button:
            if not search_name.strip():
                st.error("Please enter a name")
            else:
                # Get current tag weights
                tag_weights = {tw["tag"]: tw["weight"] for tw in tracker_db.list_tag_weights()}

                # Get current markets from session
                current_markets = st.session_state.get("job_discovery_markets", [])

                # Get current sources and location from session (set when user changes them)
                current_sources = st.session_state.get("current_sources", [])
                current_location = st.session_state.get("current_location", "")

                try:
                    search_id = tracker_db.save_search_config(
                        name=search_name.strip(),
                        tag_weights=tag_weights,
                        markets=current_markets,
                        sources=current_sources,
                        location=current_location
                    )
                    st.success(f"Saved: {search_name}")
                    st.rerun()
                except Exception as e:
                    if "UNIQUE constraint" in str(e):
                        st.error("A search with this name already exists")
                    else:
                        st.error(f"Failed to save: {e}")

# --- Search Tags Management ---
with st.expander("Search Tags & Weights", expanded=False):
    st.caption("Configure search tags and their weights (%). All active tag weights must sum to 100%.")

    tags = tracker_db.list_search_tags(active_only=False)
    tag_weights = {tw["tag"]: tw["weight"] for tw in tracker_db.list_tag_weights()}

    # Initialize draft mode session state
    if "draft_mode" not in st.session_state:
        st.session_state["draft_mode"] = False
    if "draft_weights" not in st.session_state:
        st.session_state["draft_weights"] = {}

    if tags:
        # Calculate current active tag weights and total
        active_tags = [t for t in tags if bool(t.get("active", True))]
        active_weights = {t["tag"]: tag_weights.get(t["tag"], 50) for t in active_tags}
        weight_sum = sum(active_weights.values())

        # Display each tag
        for tag in tags:
            col1, col2, col3, col4 = st.columns([3, 1, 2, 1])
            col1.text(tag["tag"])
            active = bool(tag.get("active", True))
            col2.caption("✓ Active" if active else "✗ Inactive")

            # Weight slider (only enabled for active tags)
            current_weight = tag_weights.get(tag["tag"], 50)
            # Use draft weight if in draft mode, otherwise use current weight
            display_weight = st.session_state["draft_weights"].get(tag["tag"], current_weight) if st.session_state["draft_mode"] else current_weight

            new_weight = col3.slider(
                "Weight %",
                min_value=0,
                max_value=100,
                value=display_weight,
                key=f"weight_{tag['id']}",
                label_visibility="collapsed",
                disabled=not active
            )

            # Store changes in draft mode without rerunning
            if new_weight != current_weight and active:
                st.session_state["draft_mode"] = True
                st.session_state["draft_weights"][tag["tag"]] = new_weight

            if col4.button("Toggle", key=f"toggle_{tag['id']}"):
                tracker_db.toggle_search_tag(tag["id"], not active)
                st.rerun()

        # Display draft mode controls
        if st.session_state["draft_mode"]:
            st.markdown("---")
            st.warning("⚠️ You have unsaved weight changes.")
            col_apply, col_discard = st.columns(2)

            if col_apply.button("✅ Apply Changes", type="primary"):
                # Apply all draft weights to database
                for tag_name, new_weight in st.session_state["draft_weights"].items():
                    tracker_db.set_tag_weight(tag_name, new_weight)
                # Clear draft mode
                st.session_state["draft_mode"] = False
                st.session_state["draft_weights"] = {}
                st.rerun()

            if col_discard.button("❌ Discard Changes"):
                # Clear draft mode without saving
                st.session_state["draft_mode"] = False
                st.session_state["draft_weights"] = {}
                st.rerun()

        # Display total weight validation
        st.markdown("---")
        if weight_sum == 100:
            st.success(f"✓ Total weight: {weight_sum}% (Ready to search)")
        elif weight_sum < 100:
            st.error(f"✗ Total weight: {weight_sum}% (Need {100 - weight_sum}% more)")
        else:
            st.error(f"✗ Total weight: {weight_sum}% (Reduce by {weight_sum - 100}%)")
    else:
        st.info("No search tags configured. Add some below.")

    with st.form("add_tag"):
        new_col1, new_col2 = st.columns([3, 1])
        new_tag = new_col1.text_input("New search tag", placeholder="e.g., Director of Product Design")

        # Calculate default weight suggestion (remaining percentage / 2, or 20 if sum is 0)
        remaining_pct = 100 - weight_sum if weight_sum < 100 else 20
        suggested_weight = max(1, min(100, remaining_pct // 2)) if active_tags else 100

        new_weight = new_col2.number_input("Initial weight %", min_value=0, max_value=100, value=suggested_weight)
        submitted = st.form_submit_button("Add Tag")
        if submitted:
            if new_tag.strip():
                result = tracker_db.add_search_tag(new_tag.strip())
                if result:
                    tracker_db.set_tag_weight(new_tag.strip(), new_weight)
                    st.success(f"Added tag: {new_tag.strip()} (weight: {new_weight}%)")
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

# Check if we have loaded values from a saved search
default_location = st.session_state.pop("loaded_location", "")
location = st.text_input("Location filter", placeholder="e.g., San Francisco, Remote", value=default_location)
st.session_state["current_location"] = location

# Check if we have loaded sources from a saved search
default_sources = st.session_state.pop("loaded_sources", ["indeed"])
sources = st.multiselect(
    "Job boards to search",
    options=["indeed", "linkedin", "wellfound"],
    default=default_sources,
)
st.session_state["current_sources"] = sources
st.caption("Note: Web scraping results vary. If no results appear, try different tags or check the Search Details after running.")

if "linkedin" in sources:
    st.info(
        "LinkedIn may return limited results due to anti-bot protections. "
        "Indeed usually returns more consistent results."
    )

# Search controls
col_search, col_pause, col_stop = st.columns([1, 1, 1])

# Initialize session state for search control
if "search_paused" not in st.session_state:
    st.session_state["search_paused"] = False
if "search_session_id" not in st.session_state:
    st.session_state["search_session_id"] = None

if col_search.button("🔍 Start Search", type="primary"):
    active_tags = tracker_db.list_search_tags(active_only=True)
    tag_strings = [t["tag"] for t in active_tags]

    # Validate tag weights sum to 100%
    tag_weights_active = {tw["tag"]: tw["weight"] for tw in tracker_db.list_tag_weights() if tw["tag"] in tag_strings}
    weight_sum = sum(tag_weights_active.values())

    if not tag_strings:
        st.error("No active search tags. Add and activate tags first.")
    elif not selected_markets:
        st.error("Select at least one market to search.")
    elif weight_sum != 100:
        st.error(f"Tag weights must sum to 100% (currently {weight_sum}%). Adjust weights above.")
    else:
        # Create search session
        session_id = tracker_db.create_search_session(tag_strings, selected_markets, sources)
        st.session_state["search_session_id"] = session_id
        st.session_state["search_paused"] = False

        progress_bar = st.progress(0)
        status_text = st.empty()

        def pause_check():
            return st.session_state.get("search_paused", False)

        def progress_callback(current, total):
            total_combinations = len(tag_strings) * len(sources) * len(selected_markets)
            progress = current / total_combinations if total_combinations > 0 else 0
            progress_bar.progress(min(progress, 1.0))
            status_text.text(f"Searching... {current}/{total_combinations} combinations, {total} results found")

        from jseeker.job_discovery import save_discoveries, search_jobs_async, rank_discoveries_by_tag_weight

        discoveries = search_jobs_async(
            tag_strings,
            location=location,
            sources=sources,
            markets=selected_markets,
            pause_check=pause_check,
            progress_callback=progress_callback,
            max_results=250
        )

        # Rank by tag weights
        ranked_discoveries = rank_discoveries_by_tag_weight(discoveries)

        # Save to database
        saved = save_discoveries(ranked_discoveries)

        # Update session
        tracker_db.update_search_session(
            session_id,
            status="completed" if not st.session_state["search_paused"] else "paused",
            total_found=len(discoveries),
            limit_reached=(len(discoveries) >= 250)
        )

        if len(discoveries) >= 250:
            st.warning(f"⚠️ Search limit reached: 250 results. Some results may have been skipped.")
        elif st.session_state["search_paused"]:
            st.info(f"Search paused at {len(discoveries)} results.")
        else:
            st.success(f"Found {len(discoveries)} jobs, {saved} new (deduplicated)")

        # Show search diagnostics
        with st.expander("Search Details", expanded=False):
            st.caption(f"Searched {len(tag_strings)} tag(s) x {len(sources)} source(s) x {len(selected_markets)} market(s)")
            st.caption(f"= {len(tag_strings) * len(sources) * len(selected_markets)} search combinations")
            st.caption(f"Total results before dedup: {len(discoveries)}")
            st.caption(f"New results saved: {saved}")
            st.caption(f"Results ranked by tag weights: {sum(d.search_tag_weights.values() if d.search_tag_weights else 0 for d in ranked_discoveries[:10])} total weight in top 10")

if col_pause.button("⏸️ Pause"):
    st.session_state["search_paused"] = True
    st.info("Search will pause after current combination completes.")

if col_stop.button("⏹️ Stop"):
    if st.session_state.get("search_session_id"):
        tracker_db.update_search_session(
            st.session_state["search_session_id"],
            status="stopped"
        )
    st.session_state["search_paused"] = True
    st.session_state["search_session_id"] = None
    st.warning("Search stopped.")

# --- Results ---
st.markdown("---")
st.subheader("Discovered Jobs")

# Filters
col1, col2, col3, col4 = st.columns(4)

status_filter = col1.selectbox(
    "Status",
    options=["All", "new", "starred", "dismissed", "imported"],
)

market_filter = col2.selectbox(
    "Market",
    options=["All"] + list(market_options.keys()),
    format_func=lambda x: market_options.get(x, x) if x != "All" else "All"
)

source_filter = col3.selectbox(
    "Source",
    options=["All", "indeed", "linkedin", "wellfound"],
)

location_filter = col4.text_input(
    "Location",
    placeholder="e.g., Remote, SF",
)

search_query = st.text_input(
    "Search discovered jobs",
    placeholder="Title, company, location, source, or tag",
)

# Apply filters
status_value = None if status_filter == "All" else status_filter
market_value = None if market_filter == "All" else market_filter
source_value = None if source_filter == "All" else source_filter
location_value = location_filter.strip() if location_filter.strip() else None

@st.cache_data(ttl=10)
def _get_discoveries(status, search, market, location, source):
    """Cached DB query for discoveries with 10-second TTL."""
    return tracker_db.list_discoveries(
        status=status,
        search=search,
        market=market,
        location=location,
        source=source
    )

discoveries = _get_discoveries(
    status=status_value,
    search=search_query,
    market=market_value,
    location=location_value,
    source=source_value
)

if discoveries:
    discoveries.sort(
        key=lambda d: (d.get("posting_date") or "", d.get("discovered_at") or ""),
        reverse=True,
    )

if discoveries:
    # Group discoveries by hierarchical location: Country > State/Province > City
    from collections import defaultdict

    def parse_location_hierarchy(location_str, market_code):
        """
        Parse location string into (country, state, city) tuple.

        Handles formats:
        - "City, State, Country"
        - "City, Country"
        - "State, Country"
        - "Country"
        - "Remote" or other special values
        """
        if not location_str or location_str.strip().lower() in ["remote", "unknown", "anywhere"]:
            return ("Remote/Other", "", location_str or "Unknown")

        parts = [p.strip() for p in location_str.split(",")]

        # Reverse to get country first
        parts.reverse()

        country = parts[0] if parts else "Unknown"
        state = parts[1] if len(parts) > 1 else ""
        city = parts[2] if len(parts) > 2 else ""

        # If only 2 parts, second is city (no state)
        if len(parts) == 2:
            state = ""
            city = parts[1]

        return (country, state, city)

    # Build 3-level nested structure
    by_location_hierarchy = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for d in discoveries:
        market = d.get("market") or "unknown"
        location = d.get("location") or "Unknown Location"
        country, state, city = parse_location_hierarchy(location, market)
        by_location_hierarchy[country][state][city].append(d)

    # Country emoji mapping
    COUNTRY_EMOJIS = {
        "United States": "🇺🇸",
        "Mexico": "🇲🇽",
        "Canada": "🇨🇦",
        "United Kingdom": "🇬🇧",
        "Spain": "🇪🇸",
        "Denmark": "🇩🇰",
        "France": "🇫🇷",
        "Germany": "🇩🇪",
    }

    # Sort countries
    sorted_countries = sorted(by_location_hierarchy.keys())

    # Helper function to render job card
    def render_job_card(disc):
        """Render a single job discovery card."""
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

    # Display with 3-level hierarchy: Country > State > City
    for country in sorted_countries:
        states = by_location_hierarchy[country]
        country_total = sum(len(jobs) for state_cities in states.values() for jobs in state_cities.values())
        country_emoji = COUNTRY_EMOJIS.get(country, "🌍")

        with st.expander(f"{country_emoji} {country.upper()} ({country_total} jobs)", expanded=False):
            sorted_states = sorted(states.keys())

            for state in sorted_states:
                cities = states[state]
                state_total = sum(len(jobs) for jobs in cities.values())

                # If no state/province, skip that level and go straight to cities
                if not state:
                    sorted_cities = sorted(cities.keys())
                    for city in sorted_cities:
                        city_jobs = cities[city]
                        with st.expander(f"📍 {city} ({len(city_jobs)} jobs)", expanded=False):
                            for disc in city_jobs:
                                render_job_card(disc)
                else:
                    # State/province level exists
                    with st.expander(f"📌 {state} ({state_total} jobs)", expanded=False):
                        sorted_cities = sorted(cities.keys())
                        for city in sorted_cities:
                            city_jobs = cities[city]
                            with st.expander(f"📍 {city} ({len(city_jobs)} jobs)", expanded=False):
                                for disc in city_jobs:
                                    render_job_card(disc)
else:
    st.info("No discovered jobs match your current filters. Run a search above.")
