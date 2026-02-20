"""JSEEKER Job Discovery - Tag-based job search across boards."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from jseeker.tracker import tracker_db

st.title("Job Discovery")

# --- Session state initialization ---
if "draft_mode" not in st.session_state:
    st.session_state["draft_mode"] = False
if "draft_weights" not in st.session_state:
    st.session_state["draft_weights"] = {}
if "tag_weight_key_ver" not in st.session_state:
    st.session_state["tag_weight_key_ver"] = 0
if "search_paused" not in st.session_state:
    st.session_state["search_paused"] = False
if "search_session_id" not in st.session_state:
    st.session_state["search_session_id"] = None
if "cached_search_results" not in st.session_state:
    st.session_state["cached_search_results"] = None
if "cached_search_params" not in st.session_state:
    st.session_state["cached_search_params"] = None
if "cached_search_timestamp" not in st.session_state:
    st.session_state["cached_search_timestamp"] = None
if "ranked_discoveries_cache" not in st.session_state:
    st.session_state["ranked_discoveries_cache"] = None
if "ranked_discoveries_filter_key" not in st.session_state:
    st.session_state["ranked_discoveries_filter_key"] = None
if "disc_page" not in st.session_state:
    st.session_state["disc_page"] = 0
if "market_key_ver" not in st.session_state:
    st.session_state["market_key_ver"] = 0
if "discovery_time_window" not in st.session_state:
    st.session_state["discovery_time_window"] = "All time"

# Load known application URLs for dedup badges
_known_app_urls: dict[str, str] = tracker_db.get_known_application_urls()

# --- Saved Searches Sidebar ---
with st.sidebar:
    st.subheader("Saved Searches")

    saved_searches = tracker_db.list_saved_searches()

    if saved_searches:
        # Display saved searches
        for search in saved_searches:
            with st.expander(f"📌 {search['name']}", expanded=False):
                st.caption(f"Tags: {', '.join(search['tag_weights'].keys())}")
                if search.get("markets"):
                    st.caption(f"Markets: {', '.join(search['markets'])}")
                if search.get("sources"):
                    st.caption(f"Sources: {', '.join(search['sources'])}")
                if search.get("location"):
                    st.caption(f"Location: {search['location']}")

                col1, col2, col3 = st.columns(3)

                # Load button
                if col1.button("Load", key=f"load_{search['id']}"):
                    # Restore search tags + weights from saved config.
                    # Saved tag_weights may contain junk entries (test data,
                    # non-search labels) from old save logic — filter them
                    # against actual search_tags in the DB.
                    current_tags = tracker_db.list_search_tags(active_only=False)
                    known_search_tags = {t["tag"] for t in current_tags}

                    # Only consider saved tags that are real search tags
                    valid_saved_tags = {
                        tag: weight
                        for tag, weight in search["tag_weights"].items()
                        if tag in known_search_tags
                    }

                    # Activate saved tags, deactivate the rest
                    for t in current_tags:
                        should_be_active = t["tag"] in valid_saved_tags
                        is_active = int(t.get("active", 1)) == 1
                        if should_be_active != is_active:
                            tracker_db.toggle_search_tag(t["id"], should_be_active)

                    # Set weights only for valid search tags
                    for tag, weight in valid_saved_tags.items():
                        tracker_db.set_tag_weight(tag, weight)

                    # Load markets
                    if search.get("markets"):
                        st.session_state["job_discovery_markets"] = search["markets"]

                    # Store sources and location in session for later UI sync
                    if search.get("sources"):
                        st.session_state["loaded_sources"] = search["sources"]
                    if search.get("location"):
                        st.session_state["loaded_location"] = search["location"]

                    # Bump key versions to force widget reinitialization
                    st.session_state["tag_weight_key_ver"] += 1
                    st.session_state["market_key_ver"] += 1
                    # Invalidate tag weights cache so fragment re-reads from DB
                    st.session_state["tag_weights_dirty"] = True
                    # Clear stale draft state
                    st.session_state["draft_mode"] = False
                    st.session_state["draft_weights"] = {}
                    # Force re-ranking with new weights
                    st.session_state["ranked_discoveries_cache"] = None

                    # Load from DB cache instead of re-scraping
                    st.session_state["auto_run_search"] = "from_db"

                    st.success(f"Loaded: {search['name']}")
                    st.rerun()

                # Delete button
                if col2.button("Delete", key=f"delete_{search['id']}"):
                    if tracker_db.delete_saved_search(search["id"]):
                        st.success(f"Deleted: {search['name']}")
                        st.rerun()
                    else:
                        st.error("Failed to delete")

                # Update button — overwrite saved config with current settings
                if col3.button("Update", key=f"update_{search['id']}"):
                    active_tags_for_save = {
                        t["tag"]
                        for t in tracker_db.list_search_tags(active_only=True)
                    }
                    current_tw = {
                        tw["tag"]: tw["weight"]
                        for tw in tracker_db.list_tag_weights()
                        if tw["tag"] in active_tags_for_save
                    }
                    if tracker_db.update_saved_search(
                        search["id"],
                        tag_weights=current_tw,
                        markets=st.session_state.get(
                            "job_discovery_markets", []
                        ),
                        sources=st.session_state.get("current_sources", []),
                        location=st.session_state.get("current_location", ""),
                    ):
                        st.success(f"Updated: {search['name']}")
                        st.rerun()
                    else:
                        st.error("Failed to update")

                # Rename form
                with st.form(key=f"rename_form_{search['id']}"):
                    new_name = st.text_input(
                        "Rename",
                        value=search["name"],
                        key=f"rename_input_{search['id']}",
                    )
                    if st.form_submit_button("✏️ Rename"):
                        if not new_name.strip():
                            st.error("Name cannot be empty")
                        elif new_name.strip() == search["name"]:
                            st.info("No change")
                        else:
                            try:
                                if tracker_db.update_saved_search(
                                    search["id"], name=new_name.strip()
                                ):
                                    st.success(f"Renamed to: {new_name.strip()}")
                                    st.rerun()
                                else:
                                    st.error("Failed to rename")
                            except Exception as e:
                                if "UNIQUE constraint" in str(e):
                                    st.error("A search with this name already exists")
                                else:
                                    st.error(f"Failed to rename: {e}")
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
                # Get current tag weights — only for active search tags
                # (tag_weights table may contain junk entries from tests/other features)
                active_search_tags = {
                    t["tag"] for t in tracker_db.list_search_tags(active_only=True)
                }
                tag_weights = {
                    tw["tag"]: tw["weight"]
                    for tw in tracker_db.list_tag_weights()
                    if tw["tag"] in active_search_tags
                }

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
                        location=current_location,
                    )
                    st.success(f"Saved: {search_name}")
                    st.rerun()
                except Exception as e:
                    if "UNIQUE constraint" in str(e):
                        st.error("A search with this name already exists")
                    else:
                        st.error(f"Failed to save: {e}")


# --- Search Tags Management (fragment to avoid full-page reruns on slider changes) ---
@st.fragment
def _tag_weights_fragment():
    """Render the Search Tags & Weights expander as an isolated fragment."""
    with st.expander("Search Tags & Weights", expanded=False):
        st.caption(
            "Configure search tags and their weights (%). All active tag weights must sum to 100%."
        )

        tags = tracker_db.list_search_tags(active_only=False)
        # Cache tag weights in session state — avoids a DB query on every slider drag.
        # Invalidated when Apply Changes saves new weights (sets tag_weights_dirty=True).
        if st.session_state.get("tag_weights_dirty", True):
            _tw = {tw["tag"]: tw["weight"] for tw in tracker_db.list_tag_weights()}
            st.session_state["_cached_tag_weights"] = _tw
            st.session_state["tag_weights_dirty"] = False
        tag_weights = st.session_state["_cached_tag_weights"]

        if tags:
            # Calculate current active tag weights and total
            # Use int() cast — SQLite BOOLEAN DEFAULT TRUE may store as string
            active_tags = [t for t in tags if int(t.get("active", 1)) == 1]
            active_weights = {t["tag"]: tag_weights.get(t["tag"], 50) for t in active_tags}
            weight_sum = sum(active_weights.values())

            # Display each tag
            for tag in tags:
                col1, col2, col3, col4 = st.columns([3, 1, 2, 1])
                col1.text(tag["tag"])
                active = int(tag.get("active", 1)) == 1
                col2.caption("✓ Active" if active else "✗ Inactive")

                # Weight slider (only enabled for active tags)
                current_weight = tag_weights.get(tag["tag"], 50)
                # Use draft weight if in draft mode, otherwise use current weight
                display_weight = (
                    st.session_state["draft_weights"].get(tag["tag"], current_weight)
                    if st.session_state["draft_mode"]
                    else current_weight
                )

                # Key includes version counter so Load forces reinitialization
                slider_key = f"weight_{tag['id']}_v{st.session_state.get('tag_weight_key_ver', 0)}"
                new_weight = col3.slider(
                    "Weight %",
                    min_value=0,
                    max_value=100,
                    value=display_weight,
                    key=slider_key,
                    label_visibility="collapsed",
                    disabled=not active,
                )

                # Store changes in draft mode without rerunning
                if new_weight != current_weight and active:
                    st.session_state["draft_mode"] = True
                    st.session_state["draft_weights"][tag["tag"]] = new_weight

                if col4.button("Toggle", key=f"toggle_{tag['id']}"):
                    tracker_db.toggle_search_tag(tag["id"], not active)
                    st.rerun(scope="app")

            # Display draft mode controls
            if st.session_state["draft_mode"]:
                st.markdown("---")
                st.warning("⚠️ You have unsaved weight changes.")
                col_apply, col_discard = st.columns(2)

                if col_apply.button("✅ Apply Changes", type="primary"):
                    # Apply all draft weights to database
                    for tag_name, new_weight in st.session_state["draft_weights"].items():
                        tracker_db.set_tag_weight(tag_name, new_weight)
                    # Clear draft mode and invalidate caches
                    st.session_state["draft_mode"] = False
                    st.session_state["draft_weights"] = {}
                    st.session_state["tag_weights_dirty"] = (
                        True  # force re-fetch next fragment render
                    )
                    st.session_state["ranked_discoveries_cache"] = (
                        None  # force re-rank with new weights
                    )
                    # Full rerun needed so results section re-ranks with new weights
                    st.rerun(scope="app")

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
            active_tags = []
            weight_sum = 0

        with st.form("add_tag"):
            new_col1, new_col2 = st.columns([3, 1])
            new_tag = new_col1.text_input(
                "New search tag", placeholder="e.g., Director of Product Design"
            )

            # Calculate default weight suggestion (remaining percentage / 2, or 20 if sum is 0)
            remaining_pct = 100 - weight_sum if weight_sum < 100 else 20
            suggested_weight = max(1, min(100, remaining_pct // 2)) if active_tags else 100

            new_weight = new_col2.number_input(
                "Initial weight %", min_value=0, max_value=100, value=suggested_weight
            )
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


_tag_weights_fragment()

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
    key=f"job_discovery_markets_widget_v{st.session_state.get('market_key_ver', 0)}",
)
st.session_state["job_discovery_markets"] = selected_markets

# --- Search ---
st.markdown("---")
st.subheader("Search Jobs")

# Check if we have loaded values from a saved search (persist until search executes)
default_location = st.session_state.get("loaded_location", "")
location = st.text_input(
    "Location filter", placeholder="e.g., San Francisco, Remote", value=default_location
)
st.session_state["current_location"] = location

# Sync loaded_sources into the keyed widget state (one-time on load)
if "loaded_sources" in st.session_state and "job_discovery_sources" not in st.session_state:
    st.session_state["job_discovery_sources"] = st.session_state.pop("loaded_sources")
elif "loaded_sources" in st.session_state:
    st.session_state["job_discovery_sources"] = st.session_state.pop("loaded_sources")
sources = st.multiselect(
    "Job boards to search",
    options=["indeed", "linkedin", "wellfound"],
    key="job_discovery_sources",
)
st.session_state["current_sources"] = sources
st.caption(
    "Note: Web scraping results vary. If no results appear, try different tags or check the Search Details after running."
)

if "linkedin" in sources:
    st.info(
        "LinkedIn may return limited results due to anti-bot protections. "
        "Indeed usually returns more consistent results."
    )


# Generate cache key from current search parameters
def get_cache_key(markets, location, sources):
    """Generate cache key from search parameters."""
    return {
        "markets": tuple(sorted(markets)),
        "location": location.strip().lower() if location else "",
        "sources": tuple(sorted(sources)),
    }


current_cache_key = get_cache_key(selected_markets, location, sources)

# Display cache status
cache_match = (
    st.session_state["cached_search_params"] == current_cache_key
    if st.session_state["cached_search_params"]
    else False
)

if st.session_state["cached_search_timestamp"]:
    from datetime import datetime

    cache_time = datetime.fromisoformat(st.session_state["cached_search_timestamp"])
    cache_col1, cache_col2 = st.columns([5, 1])

    if cache_match:
        cache_col1.info(
            f"💾 Using cached results from {cache_time.strftime('%Y-%m-%d %H:%M:%S')}. "
            f"Change parameters and click 'Run Search' to refresh."
        )
    else:
        cache_col1.warning(
            f"💾 Showing cached results from {cache_time.strftime('%Y-%m-%d %H:%M:%S')}. "
            f"Current parameters differ - click 'Run Search' to update."
        )

    if cache_col2.button("Clear Cache"):
        st.session_state["cached_search_results"] = None
        st.session_state["cached_search_params"] = None
        st.session_state["cached_search_timestamp"] = None
        st.session_state["ranked_discoveries_cache"] = None
        st.session_state["ranked_discoveries_filter_key"] = None
        st.rerun()

# Search controls
col_search, col_pause, col_stop = st.columns([1, 1, 1])

# Check for auto-run flag (set when loading saved search)
auto_run = st.session_state.pop("auto_run_search", False)

# Handle "from_db" mode: load cached discoveries from DB instead of re-scraping
if auto_run == "from_db":
    from jseeker.job_discovery import rank_discoveries_by_tag_weight
    from datetime import datetime

    db_discoveries = tracker_db.list_discoveries()
    if db_discoveries:
        ranked = rank_discoveries_by_tag_weight(db_discoveries, max_per_country=100)
        st.session_state["ranked_discoveries_cache"] = ranked
        st.session_state["ranked_discoveries_filter_key"] = None
        active_tags = tracker_db.list_search_tags(active_only=True)
        st.session_state["cached_search_results"] = {
            "discoveries": db_discoveries,
            "ranked_discoveries": ranked,
            "saved_count": 0,
            "tag_strings": [t["tag"] for t in active_tags],
            "search_details": {
                "tags": len(active_tags),
                "sources": len(sources),
                "markets": len(selected_markets),
                "total_combinations": 0,
                "total_found": len(db_discoveries),
                "new_saved": 0,
            },
        }
        st.session_state["cached_search_params"] = current_cache_key
        st.session_state["cached_search_timestamp"] = datetime.now().isoformat()
        st.success(f"Loaded {len(ranked)} cached jobs from database.")
    else:
        st.info("No cached results in database. Click 'Run Search' to scrape new jobs.")
    st.session_state.pop("loaded_location", None)
    st.session_state.pop("loaded_sources", None)
    auto_run = False

if col_search.button("🔍 Run Search", type="primary") or (auto_run is True):
    active_tags = tracker_db.list_search_tags(active_only=True)
    tag_strings = [t["tag"] for t in active_tags]

    # Validate tag weights sum to 100%
    # Use get_tag_weight per active tag (returns default 50 if unset) —
    # matches the display fragment's calculation exactly.
    tag_weights_active = {tag: tracker_db.get_tag_weight(tag) for tag in tag_strings}
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
            status_text.text(
                f"Searching... {current}/{total_combinations} combinations, {total} results found"
            )

        from jseeker.job_discovery import (
            save_discoveries,
            search_jobs_async,
            rank_discoveries_by_tag_weight,
        )

        discoveries = search_jobs_async(
            tag_strings,
            location=location,
            sources=sources,
            markets=selected_markets,
            pause_check=pause_check,
            progress_callback=progress_callback,
            max_results=250,
            max_results_per_country=100,
        )

        # Rank by tag weights and freshness, limit to top 100 per country
        ranked_discoveries = rank_discoveries_by_tag_weight(discoveries, max_per_country=100)

        # Save to database (needs JobDiscovery objects — must happen before dict conversion)
        saved = save_discoveries(ranked_discoveries)

        # Normalize to dicts for cache (rendering code uses .get() — works for dicts, not Pydantic)
        ranked_as_dicts = [
            d.model_dump() if hasattr(d, "model_dump") else d for d in ranked_discoveries
        ]

        # Update session
        tracker_db.update_search_session(
            session_id,
            status="completed" if not st.session_state["search_paused"] else "paused",
            total_found=len(discoveries),
            limit_reached=(len(discoveries) >= 250),
        )

        # Cache results
        from datetime import datetime

        st.session_state["cached_search_results"] = {
            "discoveries": ranked_as_dicts,
            "ranked_discoveries": ranked_as_dicts,
            "saved_count": saved,
            "tag_strings": tag_strings,
            "search_details": {
                "tags": len(tag_strings),
                "sources": len(sources),
                "markets": len(selected_markets),
                "total_combinations": len(tag_strings) * len(sources) * len(selected_markets),
                "total_found": len(discoveries),
                "new_saved": saved,
            },
        }
        st.session_state["cached_search_params"] = current_cache_key
        st.session_state["cached_search_timestamp"] = datetime.now().isoformat()
        # Store ranked results in dedicated cache (avoids re-ranking on filter/action changes)
        st.session_state["ranked_discoveries_cache"] = ranked_as_dicts
        st.session_state["ranked_discoveries_filter_key"] = None

        # Clear loaded values after search executes (prevent them from persisting)
        st.session_state.pop("loaded_location", None)
        st.session_state.pop("loaded_sources", None)

        # Display results summary
        if st.session_state["search_paused"]:
            st.info(f"Search paused at {len(discoveries)} results.")
        else:
            st.success(
                f"Search complete: Found {len(discoveries)} jobs across {len(selected_markets)} market(s), {saved} new (max 100 per market)"
            )

        # Show search diagnostics
        with st.expander("Search Details", expanded=False):
            st.caption(
                f"Searched {len(tag_strings)} tag(s) x {len(sources)} source(s) x {len(selected_markets)} market(s)"
            )
            st.caption(
                f"= {len(tag_strings) * len(sources) * len(selected_markets)} search combinations"
            )
            st.caption(f"Total results before dedup: {len(discoveries)}")
            st.caption(f"New results saved: {saved}")
            st.caption(
                f"Results ranked by tag weights: {sum(d.search_tag_weights.values() if d.search_tag_weights else 0 for d in ranked_discoveries[:10])} total weight in top 10"
            )

        # Results section below will recalculate cache_match and display results (no rerun needed)

if col_pause.button("⏸️ Pause"):
    st.session_state["search_paused"] = True
    st.info("Search will pause after current combination completes.")

if col_stop.button("⏹️ Stop"):
    if st.session_state.get("search_session_id"):
        tracker_db.update_search_session(st.session_state["search_session_id"], status="stopped")
    st.session_state["search_paused"] = True
    st.session_state["search_session_id"] = None
    st.warning("Search stopped.")

# --- Results ---
st.markdown("---")
st.subheader("Discovered Jobs")

# Recalculate cache_match (it may have been updated by search button handler above)
cache_match = (
    st.session_state["cached_search_params"] == current_cache_key
    if st.session_state["cached_search_params"]
    else False
)

# Debug: Cache diagnostics (helps diagnose display issues)
with st.expander("🐛 Debug: Cache Status", expanded=False):
    st.json(
        {
            "cache_match": cache_match,
            "cached_results_exists": st.session_state["cached_search_results"] is not None,
            "current_cache_key": current_cache_key,
            "cached_search_params": st.session_state["cached_search_params"],
            "cached_timestamp": st.session_state["cached_search_timestamp"],
            "results_count": (
                len(st.session_state["cached_search_results"]["discoveries"])
                if st.session_state["cached_search_results"]
                else 0
            ),
        }
    )

# Check if we should display cached results or prompt user to search
# PERSISTENCE FIX: Display cached results even if widgets don't match (tab navigation case)
# Only prompt to search if NO cached results exist at all
if st.session_state["cached_search_results"] is None:
    st.info(
        "👆 Configure your search parameters above, then click **Run Search** to discover jobs."
    )
    st.caption("Debug: No cached results available. Run a search to see results.")
    # Don't display results section if no cached results available
    st.stop()

# Display cached search summary
if st.session_state["cached_search_results"]:
    cached_data = st.session_state["cached_search_results"]
    search_details = cached_data.get("search_details", {})

    with st.expander("📊 Last Search Summary", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Found", search_details.get("total_found", 0))
        col2.metric("New Saved", search_details.get("new_saved", 0))
        col3.metric("Combinations", search_details.get("total_combinations", 0))
        col4.metric("Tags Used", search_details.get("tags", 0))

# Filters
col1, col2, col3, col4 = st.columns(4)

status_filter = col1.selectbox(
    "Status",
    options=["All", "new", "starred", "dismissed", "imported"],
)

market_filter = col2.selectbox(
    "Market",
    options=["All"] + list(market_options.keys()),
    format_func=lambda x: market_options.get(x, x) if x != "All" else "All",
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

# Time window filter
_time_options = ["All time", "Today", "24h", "48h", "7 days"]
time_window = st.radio(
    "Posted within",
    options=_time_options,
    index=_time_options.index(st.session_state.get("discovery_time_window", "All time")),
    horizontal=True,
    label_visibility="collapsed",
)
st.session_state["discovery_time_window"] = time_window

# Apply filters
status_value = None if status_filter == "All" else status_filter
market_value = None if market_filter == "All" else market_filter
source_value = None if source_filter == "All" else source_filter
location_value = location_filter.strip() if location_filter.strip() else None

# Use ranked cache if available; otherwise load from DB and rank once
if st.session_state["ranked_discoveries_cache"] is not None:
    _all_ranked = st.session_state["ranked_discoveries_cache"]
else:
    _all_ranked_raw = tracker_db.list_discoveries()
    if _all_ranked_raw:
        from jseeker.job_discovery import rank_discoveries_by_tag_weight

        _all_ranked = rank_discoveries_by_tag_weight(_all_ranked_raw, max_per_country=100)
        st.session_state["ranked_discoveries_cache"] = _all_ranked
    else:
        _all_ranked = []

# Apply time window filter
if time_window != "All time":
    from datetime import datetime, timedelta, date as date_type
    _now = datetime.now().date()
    _cutoffs = {"Today": 0, "24h": 1, "48h": 2, "7 days": 7}
    _days = _cutoffs.get(time_window, 0)
    _cutoff = _now - timedelta(days=_days)
    def _parse_posting_date(d):
        pd = d.get("posting_date") or d.get("posted_date")
        if not pd:
            return None
        if isinstance(pd, date_type):
            return pd
        try:
            return datetime.strptime(str(pd), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    _all_ranked = [d for d in _all_ranked if (_parse_posting_date(d) or _cutoff) >= _cutoff]

# Apply filters in-memory on the ranked cache (no DB re-query needed)
def _filter_discoveries(ranked_list, status, search, market, location_val, source):
    """Filter pre-ranked discoveries in memory."""
    result = ranked_list
    if status:
        result = [d for d in result if str(d.get("status", "new")).strip().lower() == status]
    if market:
        result = [d for d in result if (d.get("market") or "").lower() == market.lower()]
    if source:
        result = [d for d in result if (d.get("source") or "").lower() == source.lower()]
    if location_val:
        loc_lower = location_val.lower()
        result = [d for d in result if loc_lower in (d.get("location") or "").lower()]
    if search:
        q = search.lower()
        result = [
            d
            for d in result
            if (
                q in (d.get("title") or "").lower()
                or q in (d.get("company") or "").lower()
                or q in (d.get("location") or "").lower()
                or q in (d.get("source") or "").lower()
                or any(q in tag.lower() for tag in (d.get("search_tag_weights") or {}).keys())
            )
        ]
    return result


def _update_cached_discovery_status(disc_id, new_status):
    """Update a discovery's status in the ranked cache in-place."""
    cache = st.session_state.get("ranked_discoveries_cache")
    if cache:
        for d in cache:
            if d.get("id") == disc_id:
                d["status"] = new_status
                break


discoveries = _filter_discoveries(
    _all_ranked,
    status=status_value,
    search=search_query,
    market=market_value,
    location_val=location_value,
    source=source_value,
)

# --- Pagination ---
PAGE_SIZE = 50

# Detect filter changes and reset to page 0
_filter_hash = (status_value, search_query, market_value, location_value, source_value, time_window)
if st.session_state.get("_disc_filter_hash") != _filter_hash:
    st.session_state["_disc_filter_hash"] = _filter_hash
    st.session_state["disc_page"] = 0

if discoveries:
    total_pages = max(1, (len(discoveries) - 1) // PAGE_SIZE + 1)
    # Clamp page to valid range
    st.session_state["disc_page"] = min(st.session_state["disc_page"], total_pages - 1)
    current_page = st.session_state["disc_page"]

    # Pagination controls
    pg_col1, pg_col2, pg_col3 = st.columns([1, 2, 1])
    if pg_col1.button("◀ Prev", disabled=(current_page == 0)):
        st.session_state["disc_page"] -= 1
        st.rerun()
    pg_col2.markdown(
        f"<div style='text-align:center'>Page {current_page + 1} of {total_pages} "
        f"({len(discoveries)} jobs)</div>",
        unsafe_allow_html=True,
    )
    if pg_col3.button("Next ▶", disabled=(current_page >= total_pages - 1)):
        st.session_state["disc_page"] += 1
        st.rerun()

    # Slice to current page
    page_discoveries = discoveries[current_page * PAGE_SIZE : (current_page + 1) * PAGE_SIZE]

    # Group page discoveries by hierarchical location: Country > State/Province > City
    from collections import defaultdict

    def parse_location_hierarchy(location_str, market_code):
        """
        Parse location string into (country, state, city) tuple.

        Handles multiple formats robustly:
        - "City, State, Country" -> (Country, State, City)
        - "City, Country" -> (Country, "", City)
        - "State, Country" -> (Country, State, "")
        - "Country" -> (Country, "", "")
        - "Greater X, Country" -> (Country, "Greater X", "")
        - Just "City" -> (Market country, "", City)
        """
        # Market to country mapping
        market_countries = {
            "us": "United States",
            "mx": "Mexico",
            "ca": "Canada",
            "uk": "United Kingdom",
            "es": "Spain",
            "dk": "Denmark",
            "fr": "France",
            "de": "Germany",
        }

        if not location_str or location_str.strip().lower() in [
            "remote",
            "unknown",
            "anywhere",
        ]:
            return ("Remote/Other", "", location_str or "Unknown")

        loc = location_str.strip()

        # Handle just country name
        if loc in [
            "Canada",
            "United States",
            "Mexico",
            "Denmark",
            "Spain",
            "France",
            "Germany",
            "United Kingdom",
        ]:
            return (loc, "", "")

        parts = [p.strip() for p in loc.split(",")]

        if len(parts) == 1:
            # Just a city name - use market as country
            country = market_countries.get(market_code.lower(), "Unknown")
            return (country, "", parts[0])

        elif len(parts) == 2:
            # "City, Country" or "State, Country"
            potential_country = parts[1]
            # Check if second part is a known country
            if potential_country in market_countries.values():
                # It's a country - first part could be city or state
                if "Greater" in parts[0] or "Metropolitan" in parts[0] or "Area" in parts[0]:
                    return (potential_country, parts[0], "")  # Region/area
                else:
                    return (potential_country, "", parts[0])  # City
            else:
                # Not a recognized country, treat as city, region
                country = market_countries.get(market_code.lower(), "Unknown")
                return (country, parts[1], parts[0])

        elif len(parts) >= 3:
            # "City, State, Country" - standard format
            country = parts[-1].strip()  # Last is country
            state = parts[-2].strip()  # Second to last is state/province
            city = parts[0].strip()  # First is city
            return (country, state, city)

        return ("Unknown", "", loc)

    # --- Location normalization aliases ---
    STATE_ALIASES = {
        "New York": "NY",
        "New York City": "NY",
        "California": "CA",
        "Illinois": "IL",
        "Texas": "TX",
        "Florida": "FL",
        "Massachusetts": "MA",
        "Washington": "WA",
        "Georgia": "GA",
        "Colorado": "CO",
        "Oregon": "OR",
        "Pennsylvania": "PA",
        "Virginia": "VA",
        "North Carolina": "NC",
        "Ohio": "OH",
        "Michigan": "MI",
        "Arizona": "AZ",
        "Minnesota": "MN",
        "New Jersey": "NJ",
        "Connecticut": "CT",
        "Maryland": "MD",
        "Tennessee": "TN",
        "Indiana": "IN",
        "Missouri": "MO",
        "Wisconsin": "WI",
        "Nevada": "NV",
        "Utah": "UT",
        "District of Columbia": "DC",
        "D.C.": "DC",
        "New York City Metropolitan Area": "NY",
        "Greater New York City Area": "NY",
        # Canadian provinces
        "British Columbia": "BC",
        "Greater Vancouver": "BC",
        "Ontario": "ON",
        "Quebec": "QC",
        "Alberta": "AB",
    }

    CITY_ALIASES = {
        "New York City": "New York",
        "NYC": "New York",
        "New York City Metropolitan Area": "New York",
        "Greater New York City Area": "New York",
        "México": "Mexico City",
        "CDMX": "Mexico City",
        "Ciudad de México": "Mexico City",
        "Mexico City Metropolitan Area": "Mexico City",
        "Greater Mexico City": "Mexico City",
        "Mexico Metropolitan Area": "Mexico City",
        "Mexico metropolitan area": "Mexico City",
        "San Francisco Bay Area": "San Francisco",
        "SF": "San Francisco",
        "Greater Los Angeles": "Los Angeles",
        "LA": "Los Angeles",
        "Greater Toronto Area": "Toronto",
        "GTA": "Toronto",
        "Greater Vancouver Area": "Vancouver",
        "Greater Vancouver": "Vancouver",
        "Greater London": "London",
        "Greater Copenhagen": "Copenhagen",
        "Greater Barcelona": "Barcelona",
    }

    def normalize_location(country, state, city):
        """Normalize state abbreviations and city name variants to canonical forms."""
        # Normalize state
        if state in STATE_ALIASES:
            state = STATE_ALIASES[state]

        # Normalize city
        if city in CITY_ALIASES:
            city = CITY_ALIASES[city]

        # Fuzzy normalization for "Greater X" and "X Metropolitan Area" patterns
        if "Metropolitan" in city or "Greater" in city:
            clean = (
                city.replace("Greater ", "")
                .replace(" Metropolitan Area", "")
                .replace(" Metropolitan area", "")
                .replace(" Area", "")
                .strip()
            )
            if clean in CITY_ALIASES:
                city = CITY_ALIASES[clean]
            elif clean:
                city = clean

        # Special case: city is a state name (e.g. "New York City" parsed as city with no state)
        if not state and city in STATE_ALIASES:
            state = STATE_ALIASES[city]
            city = CITY_ALIASES.get(city, city)

        return (country, state, city)

    # Deduplicate by URL (keep first occurrence — highest ranked)
    seen_urls = set()
    deduped_discoveries = []
    for d in page_discoveries:
        url = d.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        deduped_discoveries.append(d)

    # Build 3-level nested structure from page slice
    by_location_hierarchy = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for d in deduped_discoveries:
        market = d.get("market") or "unknown"
        location = d.get("location") or "Unknown Location"
        country, state, city = parse_location_hierarchy(location, market)
        country, state, city = normalize_location(country, state, city)
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

    # Calculate relevance averages for sorting
    def calc_avg_relevance(jobs_list):
        """Calculate average composite score for a list of jobs."""
        if not jobs_list:
            return 0.0
        scores = [j.get("composite_score", 0.0) for j in jobs_list]
        return sum(scores) / len(scores) if scores else 0.0

    # Sort countries by average relevance (high to low)
    country_avgs = {}
    for country, states in by_location_hierarchy.items():
        all_jobs = [
            job
            for state_cities in states.values()
            for city_jobs in state_cities.values()
            for job in city_jobs
        ]
        country_avgs[country] = calc_avg_relevance(all_jobs)

    sorted_countries = sorted(
        by_location_hierarchy.keys(), key=lambda c: country_avgs[c], reverse=True
    )

    # Helper function to render job card
    def render_job_card(disc):
        """Render a single job discovery card."""
        from jseeker.job_discovery import format_freshness

        with st.container():
            # Get composite score (0-1 scale) and convert to 0-100
            composite_score = disc.get("composite_score", 0.0)
            score_pct = int(composite_score * 100)

            # Determine if this is a "suggested" job (>90% relevance)
            is_suggested = score_pct >= 90

            # Main info row: title, company, score badge
            col1, col2, col3 = st.columns([5, 2, 2])

            # Title with optional suggested badge
            title_text = f"**{disc['title']}** - {disc.get('company', '')}"
            if is_suggested:
                title_text = f"⭐ {title_text}"
            col1.markdown(title_text)

            # Display relevance score prominently
            if score_pct >= 90:
                score_color = "🟢"
            elif score_pct >= 70:
                score_color = "🟡"
            else:
                score_color = "🔵"
            col2.caption(f"{score_color} **{score_pct}%** relevance")

            # Display freshness
            posting_date = disc.get("posting_date", "")
            freshness_text = format_freshness(posting_date)
            col3.caption(f"🕒 {freshness_text}")

            # Second row: Location + source + score breakdown expander
            location = disc.get("location", "Unknown")
            source = disc.get("source", "")
            st.caption(f"📍 {location} · {source}")

            # Dedup badge — check if already in tracker
            _job_url = disc.get("url", "")
            if _job_url and _job_url in _known_app_urls:
                _app_status = _known_app_urls[_job_url]
                if _app_status in ("applied", "applied_verified"):
                    st.caption("✅ **Applied** · Already in tracker")
                elif _app_status == "easy_apply":
                    st.caption("🟦 **Easy Apply** · Already in tracker")
                else:
                    st.caption("📥 **In Tracker** · Already imported")

            # Score breakdown in expandable section
            with st.expander("📊 Score Breakdown", expanded=False):
                tag_contrib = disc.get("tag_weight_contribution", 0.0) * 100
                resume_contrib = disc.get("resume_match_contribution", 0.0) * 100
                fresh_contrib = disc.get("freshness_contribution", 0.0) * 100

                st.caption(f"**Composite Score: {score_pct}%**")
                st.caption(f"├─ Tag Match: {tag_contrib:.1f}% (70% weight)")
                st.caption(f"├─ Resume Match: {resume_contrib:.1f}% (30% weight)")
                st.caption(f"└─ Freshness Bonus: {fresh_contrib:.1f}%")

                # Show which tags matched
                tag_weights = disc.get("search_tag_weights", {})
                if tag_weights:
                    st.caption("**Matching Tags:**")
                    for tag, weight in sorted(
                        tag_weights.items(), key=lambda x: x[1], reverse=True
                    ):
                        st.caption(f"  • {tag}: {weight}%")

            # Action buttons row
            action_cols = st.columns(5)
            status = str(disc.get("status", "new")).strip().lower()

            if status == "new":
                if action_cols[0].button("Star", key=f"star_{disc['id']}"):
                    tracker_db.update_discovery_status(disc["id"], "starred")
                    # Update cached list in-place to avoid re-ranking
                    _update_cached_discovery_status(disc["id"], "starred")
                    st.toast("⭐ Starred!")
                    st.rerun()
                if action_cols[1].button("Dismiss", key=f"dismiss_{disc['id']}"):
                    tracker_db.update_discovery_status(disc["id"], "dismissed")
                    _update_cached_discovery_status(disc["id"], "dismissed")
                    st.toast("👋 Dismissed")
                    st.rerun()

            if status in ("new", "starred"):
                if action_cols[2].button("Quick Import", key=f"import_{disc['id']}"):
                    from jseeker.job_discovery import import_discovery_to_application

                    app_id = import_discovery_to_application(disc["id"])
                    if app_id:
                        _update_cached_discovery_status(disc["id"], "imported")
                        st.toast("Imported to Tracker!")
                        st.success(f"Imported as application #{app_id} (no resume generated)")
                    else:
                        st.error("Failed to import")
                    st.rerun()

            if status in ("new", "starred"):
                if action_cols[3].button("Generate Resume", key=f"gen_{disc['id']}"):
                    with st.spinner(f"Generating resume for {disc.get('company', 'Unknown')}..."):
                        from jseeker.job_discovery import generate_resume_from_discovery

                        result = generate_resume_from_discovery(disc["id"])
                        if result:
                            _update_cached_discovery_status(disc["id"], "imported")
                            st.toast(f"Resume generated! ATS: {result['ats_score']}%")
                            st.success(
                                f"Resume created for {result['company']} - {result['role']} "
                                f"(ATS: {result['ats_score']}%, Relevance: {result['relevance_score']}%)"
                            )
                        else:
                            st.error(
                                "Failed to generate resume. JD extraction may have failed — try manual entry in New Resume."
                            )
                    st.rerun()

            if disc.get("url"):
                action_cols[4].markdown(f"[View Job]({disc['url']})")

            st.markdown("---")

    # Display with 3-level hierarchy: Country > State > City
    for country in sorted_countries:
        states = by_location_hierarchy[country]
        country_total = sum(
            len(jobs) for state_cities in states.values() for jobs in state_cities.values()
        )
        country_emoji = COUNTRY_EMOJIS.get(country, "🌍")
        country_avg = country_avgs[country]
        country_avg_pct = int(country_avg * 100)

        with st.expander(
            f"{country_emoji} {country} · {country_total} jobs · avg: {country_avg_pct}%",
            expanded=False,
        ):
            # Calculate state averages for sorting
            state_avgs = {}
            for state, cities in states.items():
                all_jobs = [job for city_jobs in cities.values() for job in city_jobs]
                state_avgs[state] = calc_avg_relevance(all_jobs)
            sorted_states = sorted(states.keys(), key=lambda s: state_avgs[s], reverse=True)

            for state in sorted_states:
                cities = states[state]
                state_total = sum(len(jobs) for jobs in cities.values())

                # Calculate city averages for sorting
                city_avgs = {city: calc_avg_relevance(jobs) for city, jobs in cities.items()}

                # If no state/province, skip that level and go straight to cities
                if not state:
                    sorted_cities = sorted(cities.keys(), key=lambda c: city_avgs[c], reverse=True)
                    for city in sorted_cities:
                        city_jobs = cities[city]
                        city_avg_pct = int(city_avgs[city] * 100)
                        with st.expander(
                            f"📍 {city} · {len(city_jobs)} jobs · avg: {city_avg_pct}%",
                            expanded=False,
                        ):
                            for disc in city_jobs:
                                render_job_card(disc)
                else:
                    # State/province level exists
                    state_avg_pct = int(state_avgs[state] * 100)
                    with st.expander(
                        f"📌 {state} · {state_total} jobs · avg: {state_avg_pct}%",
                        expanded=False,
                    ):
                        sorted_cities = sorted(
                            cities.keys(), key=lambda c: city_avgs[c], reverse=True
                        )
                        for city in sorted_cities:
                            city_jobs = cities[city]
                            city_avg_pct = int(city_avgs[city] * 100)
                            with st.expander(
                                f"📍 {city} · {len(city_jobs)} jobs · avg: {city_avg_pct}%",
                                expanded=False,
                            ):
                                for disc in city_jobs:
                                    render_job_card(disc)
else:
    st.info("No discovered jobs match your current filters. Run a search above.")
