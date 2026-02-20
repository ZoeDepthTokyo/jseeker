"""Analytics — Pattern Learning and Salary & Markets intelligence dashboard."""

import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import settings
from jseeker.llm import llm
from jseeker.pattern_learner import get_pattern_stats
from jseeker.tracker import tracker_db


@st.cache_data(ttl=60)
def _cached_get_pattern_stats(db_path_str: str):
    """Cache pattern stats for 60 seconds."""
    from pathlib import Path as _Path

    return get_pattern_stats(db_path=_Path(db_path_str))


@st.cache_data(ttl=60)
def _cached_cost_data(db_path_str: str):
    """Cache API cost records for 60 seconds."""
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(db_path_str)
    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(cost_usd), 0) as total
        FROM api_costs
        WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')
    """)
    monthly_cost = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM resumes")
    total_resumes = c.fetchone()[0]
    c.execute("""
        SELECT DATE(timestamp) as date, SUM(cost_usd) as daily_cost
        FROM api_costs
        GROUP BY DATE(timestamp)
        ORDER BY timestamp ASC
    """)
    cost_data = [{"date": row[0], "cost": row[1]} for row in c.fetchall()]
    conn.close()
    return monthly_cost, total_resumes, cost_data


@st.cache_data(ttl=60)
def _cached_list_applications_analytics():
    """Cache applications for analytics tab for 60 seconds."""
    return tracker_db.list_applications()


@st.cache_data(ttl=60)
def _cached_all_patterns(db_path_str: str) -> list[dict]:
    """Cache all learned patterns for 60 seconds."""
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(db_path_str)
    conn.row_factory = _sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT id, pattern_type, source_text, target_text, jd_context, "
        "frequency, confidence FROM learned_patterns ORDER BY frequency DESC"
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@st.cache_data(ttl=60)
def _cached_pattern_history(db_path_str: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Cache pattern history, timeline, and savings data for 60 seconds.

    Returns:
        Tuple of (patterns, pattern_timeline, savings_data)
    """
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(db_path_str)
    conn.row_factory = _sqlite3.Row
    c = conn.cursor()

    c.execute(
        "SELECT id, pattern_type, source_text, target_text, jd_context, "
        "frequency, confidence, created_at, last_used_at "
        "FROM learned_patterns ORDER BY created_at DESC LIMIT 50"
    )
    patterns = [dict(r) for r in c.fetchall()]

    c.execute(
        "SELECT DATE(created_at) as date, COUNT(*) as patterns_created "
        "FROM learned_patterns GROUP BY DATE(created_at) ORDER BY created_at ASC"
    )
    pattern_timeline = [{"date": row[0], "count": row[1]} for row in c.fetchall()]

    c.execute(
        "SELECT pattern_type, COUNT(*) as pattern_count, SUM(frequency) as total_uses, "
        "SUM(CASE WHEN frequency >= 3 THEN frequency ELSE 0 END) as cache_hits "
        "FROM learned_patterns GROUP BY pattern_type ORDER BY cache_hits DESC"
    )
    savings_data = []
    for row in c.fetchall():
        cost_saved = row["cache_hits"] * 0.01
        savings_data.append(
            {
                "Type": row["pattern_type"].replace("_", " ").title(),
                "Patterns": row["pattern_count"],
                "Total Uses": row["total_uses"],
                "Cache Hits": row["cache_hits"],
                "Cost Saved": f"${cost_saved:.2f}",
            }
        )

    conn.close()
    return patterns, pattern_timeline, savings_data


@st.cache_data(ttl=60)
def _cached_resume_costs(db_path_str: str) -> list[dict]:
    """Cache per-resume cost data for 60 seconds."""
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(db_path_str)
    conn.row_factory = _sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT ROW_NUMBER() OVER (ORDER BY created_at) as resume_number, generation_cost "
        "FROM resumes WHERE generation_cost IS NOT NULL AND generation_cost > 0 "
        "ORDER BY created_at ASC"
    )
    rows = c.fetchall()
    conn.close()
    return [{"resume_number": row[0], "cost": row[1]} for row in rows]

st.set_page_config(page_title="Analytics - jSeeker", page_icon="📊", layout="wide")

st.title("📊 Analytics")

# ── Shared Date-Range Filter ────────────────────────────────────────────────

_default_start = date(2020, 1, 1)
_default_end = date.today()
date_filter = st.date_input(
    "Date range",
    value=(_default_start, _default_end),
    key="analytics_date",
)

st.markdown("---")

tab1, tab2 = st.tabs(["Pattern Learning", "Salary & Markets"])

# ════════════════════════════════════════════════════════════════════
# Tab 1: Pattern Learning (from 7_learning_insights.py)
# ════════════════════════════════════════════════════════════════════

with tab1:
    st.markdown(
        "See how jSeeker learns from your feedback and optimizes costs over time. "
        "The system stores adaptation patterns and reuses them, reducing LLM calls and costs."
    )

    # ── Section 1: Pattern Learning Stats ──────────────────────────────────────

    st.markdown("---")
    st.header("📊 Pattern Learning Stats")

    try:
        stats = _cached_get_pattern_stats(str(settings.db_path))

        if stats["total_patterns"] == 0:
            st.info(
                "No patterns learned yet. Generate a few resumes to start building the pattern library."
            )
        else:
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Total Patterns", stats["total_patterns"])

            with col2:
                st.metric("Cache Hit Rate", f"{stats['cache_hit_rate']}%")

            with col3:
                st.metric("Cost Saved", f"${stats['cost_saved']:.2f}")

            st.caption(
                f"**How it works:** After generating {stats['total_uses']} adaptations, "
                f"jSeeker reused {int(stats['cache_hit_rate'])}% of them without calling the LLM, "
                f"saving approximately ${stats['cost_saved']:.2f} in API costs."
            )

            # Pattern examples table
            if stats["top_patterns"]:
                st.markdown("### Top 10 Learned Patterns")
                st.markdown("These patterns are reused most frequently across resumes:")

                pattern_df = pd.DataFrame(stats["top_patterns"])
                # Add domain column if missing (backwards compat with pre-v0.3.8 data)
                if "domain" not in pattern_df.columns:
                    pattern_df["domain"] = "General"
                pattern_df = pattern_df[
                    [
                        "id",
                        "type",
                        "domain",
                        "frequency",
                        "confidence",
                        "context",
                        "source",
                        "target",
                    ]
                ]
                pattern_df.columns = [
                    "ID",
                    "Type",
                    "Domain",
                    "Uses",
                    "Confidence",
                    "Target JD Role",
                    "Original Text",
                    "Adapted Text",
                ]

                st.dataframe(
                    pattern_df,
                    width="stretch",
                    hide_index=True,
                )

                st.caption(
                    "**Domain** = classified from the JD role and keywords. "
                    "**Target JD Role** = the job description this pattern was adapted for. "
                    "Your resume content was tailored to match each role's requirements."
                )

    except Exception as exc:
        st.error(f"Failed to load pattern stats: {exc}")

    # ── Section 2: Cost Optimization ───────────────────────────────────────────

    st.markdown("---")
    st.header("💰 Cost Optimization")

    try:
        monthly_cost, total_resumes, cost_data = _cached_cost_data(str(settings.db_path))

        # Average cost per resume
        avg_cost = monthly_cost / total_resumes if total_resumes > 0 else 0.0

        col1, col2 = st.columns(2)

        with col1:
            st.metric("Total Spent (This Month)", f"${monthly_cost:.2f}")

        with col2:
            st.metric("Avg Cost per Resume", f"${avg_cost:.3f}")

        st.markdown("""
        **Cost Optimization Over Time**: As jSeeker learns more patterns, the cache hit rate increases,
        reducing the number of expensive LLM calls needed. Your cost per resume should decrease as you
        generate more resumes.
        """)

        if cost_data:
            cost_df = pd.DataFrame(cost_data)
            cost_df["cumulative_cost"] = cost_df["cost"].cumsum()

            fig = px.line(
                cost_df,
                x="date",
                y="cumulative_cost",
                title="Cumulative API Costs Over Time",
                labels={"date": "Date", "cumulative_cost": "Total Cost ($)"},
            )
            fig.update_traces(mode="lines+markers")
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No cost data yet. Generate your first resume to start tracking.")

    except Exception as exc:
        st.error(f"Failed to load cost data: {exc}")

    # ── Section 3: Pattern Schema & Learned Tags ─────────────────────────────

    st.markdown("---")
    st.header("📋 Pattern Schema & Learned Tags")

    st.markdown(
        "Each pattern is a transformation that worked well in the past "
        "(e.g., how to adapt a bullet point for a specific role). "
        "Patterns are stored in SQLite and reused to reduce LLM calls."
    )

    try:
        all_patterns = _cached_all_patterns(str(settings.db_path))

        if all_patterns:
            # Collect all unique tags (keywords) and roles across patterns
            all_keywords = set()
            all_roles = set()
            type_counts = {}

            for row in all_patterns:
                ctx = json.loads(row["jd_context"] or "{}")
                role = ctx.get("role", "")
                if role:
                    all_roles.add(role.title())
                for kw in ctx.get("keywords", []):
                    if kw:
                        all_keywords.add(kw)
                ptype = row["pattern_type"]
                type_counts[ptype] = type_counts.get(ptype, 0) + 1

            # Summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Pattern Types", len(type_counts))
            with col2:
                st.metric("Unique Roles Targeted", len(all_roles))
            with col3:
                st.metric("Unique JD Keywords", len(all_keywords))

            # Learned roles
            if all_roles:
                st.markdown("### Targeted Roles")
                st.caption("JD roles that patterns have been learned for:")
                role_tags = "  ".join([f"`{r}`" for r in sorted(all_roles)])
                st.markdown(role_tags)

            # Learned keywords / tags
            if all_keywords:
                st.markdown("### Learned JD Keywords")
                st.caption("Keywords extracted from job descriptions during pattern learning:")
                kw_tags = "  ".join([f"`{kw}`" for kw in sorted(all_keywords)])
                st.markdown(kw_tags)

            # Pattern type breakdown
            st.markdown("### Patterns by Type")
            type_data = [
                {"Type": k.replace("_", " ").title(), "Count": v}
                for k, v in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
            ]
            st.dataframe(pd.DataFrame(type_data), width="stretch", hide_index=True)

            # Expandable individual patterns with before/after
            st.markdown("### Top Patterns (by frequency)")
            st.caption("Actual patterns learned from your resume generation history:")

            for pattern in all_patterns[:20]:
                ctx = json.loads(pattern["jd_context"] or "{}")
                role = ctx.get("role", "N/A")
                ptype = pattern["pattern_type"].replace("_", " ").title()
                label = f"#{pattern['id']} | {ptype} | {role} | {pattern['frequency']}x"

                with st.expander(label, expanded=False):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("**Pattern Details:**")
                        st.markdown(f"- **Type:** `{pattern['pattern_type']}`")
                        st.markdown(f"- **Target Role:** {role}")
                        st.markdown(f"- **Frequency:** {pattern['frequency']} uses")
                        st.markdown(f"- **Confidence:** {pattern['confidence']:.2f}")

                        keywords = ctx.get("keywords", [])
                        if keywords:
                            st.markdown(f"- **Keywords:** {', '.join(keywords[:8])}")

                        industry = ctx.get("industry")
                        if industry:
                            st.markdown(f"- **Industry:** {industry}")

                    with col2:
                        st.markdown("**Transformation:**")
                        st.markdown("Original:")
                        src = pattern["source_text"]
                        st.code(
                            src[:300] + ("..." if len(src) > 300 else ""),
                            language="text",
                        )
                        st.markdown("Adapted:")
                        tgt = pattern["target_text"]
                        st.code(
                            tgt[:300] + ("..." if len(tgt) > 300 else ""),
                            language="text",
                        )

            if len(all_patterns) > 20:
                st.caption(f"Showing top 20 of {len(all_patterns)} patterns.")

            # Show top pattern as raw JSON for schema reference
            top = all_patterns[0]
            top_ctx = json.loads(top["jd_context"] or "{}")
            st.markdown("### Pattern JSON Schema")
            st.caption("Raw JSON structure of the most-used pattern:")
            st.json(
                {
                    "id": top["id"],
                    "pattern_type": top["pattern_type"],
                    "source_text": top["source_text"][:150]
                    + ("..." if len(top["source_text"]) > 150 else ""),
                    "target_text": top["target_text"][:150]
                    + ("..." if len(top["target_text"]) > 150 else ""),
                    "jd_context": top_ctx,
                    "frequency": top["frequency"],
                    "confidence": top["confidence"],
                },
                expanded=True,
            )

        else:
            st.info("No patterns learned yet. Generate resumes to build the pattern library.")

            # Show schema documentation even with no patterns
            st.markdown("### Pattern JSON Schema")
            st.caption("Each learned pattern follows this structure:")
            st.json(
                {
                    "id": "Unique pattern identifier (integer)",
                    "pattern_type": "Category: bullet_adaptation, summary_style, skills, etc.",
                    "source_text": "Original text from resume block",
                    "target_text": "LLM-adapted or user-edited text",
                    "jd_context": {
                        "role": "Target job role (lowercase)",
                        "keywords": ["ats", "keywords", "from", "jd"],
                        "industry": "Industry classification (if available)",
                    },
                    "frequency": "Number of times reused (integer)",
                    "confidence": "Trust score 0.0-1.0",
                },
                expanded=True,
            )

    except Exception as e:
        st.warning(f"Could not load pattern data: {e}")

    # Show actual skill tags from resume blocks
    st.markdown("### Your Resume Skills (Available for Adaptation)")
    try:
        import yaml

        skills_path = Path(__file__).parent.parent.parent / "data" / "resume_blocks" / "skills.yaml"

        if skills_path.exists():
            with open(skills_path, "r", encoding="utf-8") as f:
                skills_data = yaml.safe_load(f)

            skill_categories = []
            for category_key, category_data in skills_data.get("skills", {}).items():
                category_name = category_data.get("display_name", category_key)
                skill_items = [item["name"] for item in category_data.get("items", [])]
                skill_categories.append(
                    {
                        "Category": category_name,
                        "Skills": ", ".join(skill_items[:3])
                        + ("..." if len(skill_items) > 3 else ""),
                        "Total": len(skill_items),
                    }
                )

            if skill_categories:
                st.markdown("jSeeker adapts these skills based on JD keywords:")
                skills_df = pd.DataFrame(skill_categories)
                st.dataframe(skills_df, width="stretch", hide_index=True)
        else:
            st.info("Skills file not found. Run a resume generation to populate skill tags.")

    except Exception as e:
        st.warning(f"Could not load skills data: {e}")

    st.markdown("""
**Field Explanations**:
- `pattern_type`: Category of adaptation (bullet_adaptation, summary_style, skills, etc.)
- `source_text`: Original text from the user's resume blocks
- `target_text`: Adapted text (user-edited or LLM-generated for a specific JD)
- `jd_context.role`: The job role this pattern was created for (lowercase)
- `jd_context.keywords`: ATS keywords from the JD that triggered this adaptation
- `jd_context.industry`: Industry classification when available
- `frequency`: How many times this pattern has been reused (3+ uses = trusted for cache hits)
- `confidence`: Trust score (0.0-1.0) based on source text and context similarity matching
""")

    # ── Section 4: Pattern History ────────────────────────────────────────────

    st.markdown("---")
    st.header("🔄 Pattern History")

    st.markdown("""
Track how patterns evolve and improve over time. Patterns start with low frequency and confidence,
then increase as they are validated by successful reuse.
""")

    try:
        patterns, pattern_timeline, savings_data = _cached_pattern_history(str(settings.db_path))

        if patterns:
            st.markdown(f"### Pattern Library ({len(patterns)} patterns shown)")

            # Group patterns by type
            pattern_types = {}
            for row in patterns:
                ptype = row["pattern_type"]
                if ptype not in pattern_types:
                    pattern_types[ptype] = []
                pattern_types[ptype].append(row)

            # Display grouped by type
            for ptype, type_patterns in pattern_types.items():
                with st.expander(
                    f"**{ptype.replace('_', ' ').title()}** ({len(type_patterns)} patterns)",
                    expanded=False,
                ):
                    for pattern in type_patterns:
                        # Parse JD context
                        try:
                            context = json.loads(pattern["jd_context"] or "{}")
                            role = context.get("role", "N/A")
                            keywords = ", ".join(context.get("keywords", [])[:5])
                        except (
                            json.JSONDecodeError,
                            KeyError,
                            TypeError,
                            AttributeError,
                        ):
                            role = "N/A"
                            keywords = "N/A"

                        # Display pattern details
                        col1, col2 = st.columns([3, 1])

                        with col1:
                            st.markdown(f"**Pattern #{pattern['id']}** — Learned from: *{role}*")
                            st.markdown(f"**Keywords**: {keywords if keywords else 'None'}")
                            st.caption("↑ Job role that triggered this pattern learning")

                            # Show before/after
                            st.markdown("**Before:**")
                            st.code(
                                pattern["source_text"][:200]
                                + ("..." if len(pattern["source_text"]) > 200 else ""),
                                language="text",
                            )

                            st.markdown("**After:**")
                            st.code(
                                pattern["target_text"][:200]
                                + ("..." if len(pattern["target_text"]) > 200 else ""),
                                language="text",
                            )

                        with col2:
                            st.metric("Used", f"{pattern['frequency']}x")
                            st.metric("Confidence", f"{pattern['confidence']:.2f}")

                            # Format dates
                            created = datetime.fromisoformat(pattern["created_at"]).strftime(
                                "%b %d"
                            )
                            last_used = datetime.fromisoformat(pattern["last_used_at"]).strftime(
                                "%b %d"
                            )

                            st.caption(f"Created: {created}")
                            st.caption(f"Last used: {last_used}")

                        st.markdown("---")

            # Pattern frequency over time chart
            st.markdown("### Pattern Usage Over Time")

            if pattern_timeline and len(pattern_timeline) > 1:
                timeline_df = pd.DataFrame(pattern_timeline)
                timeline_df["cumulative"] = timeline_df["count"].cumsum()

                fig = go.Figure()
                fig.add_trace(
                    go.Scatter(
                        x=timeline_df["date"],
                        y=timeline_df["cumulative"],
                        mode="lines+markers",
                        name="Total Patterns",
                        line=dict(color="blue", width=2),
                    )
                )

                fig.update_layout(
                    title="Pattern Library Growth",
                    xaxis_title="Date",
                    yaxis_title="Total Patterns",
                    hovermode="x unified",
                )

                st.plotly_chart(fig, width="stretch")
            else:
                st.info("Create more patterns over multiple days to see timeline.")

            # Cost savings breakdown
            st.markdown("### Cost Savings from Pattern Reuse")

            if savings_data:
                savings_df = pd.DataFrame(savings_data)
                st.dataframe(
                    savings_df,
                    width="stretch",
                    hide_index=True,
                )

                total_saved = sum(
                    [float(row["Cost Saved"].replace("$", "")) for row in savings_data]
                )
                st.success(f"💰 Total saved from pattern reuse: **${total_saved:.2f}**")

        else:
            st.info(
                "No patterns learned yet. Generate a few resumes and the system will start learning adaptation patterns."
            )

    except Exception as exc:
        st.error(f"Failed to load pattern history: {exc}")

    # ── Section 5: Performance Trends ──────────────────────────────────────────

    st.markdown("---")
    st.header("📈 Performance Trends")

    st.markdown("""
As the pattern library grows, each new resume should cost less to generate because
jSeeker reuses more learned patterns instead of calling the LLM.
""")

    try:
        resume_costs = _cached_resume_costs(str(settings.db_path))

        if len(resume_costs) >= 2:
            cost_df = pd.DataFrame(resume_costs)

            # Try to add trendline if statsmodels is available
            try:
                fig = px.scatter(
                    cost_df,
                    x="resume_number",
                    y="cost",
                    title="Cost per Resume Over Time (Should Decrease)",
                    labels={
                        "resume_number": "Resume Number",
                        "cost": "Generation Cost ($)",
                    },
                    trendline="lowess",
                )
            except Exception:
                # Fallback: simple scatter plot without trendline
                fig = px.scatter(
                    cost_df,
                    x="resume_number",
                    y="cost",
                    title="Cost per Resume Over Time (Should Decrease)",
                    labels={
                        "resume_number": "Resume Number",
                        "cost": "Generation Cost ($)",
                    },
                )
                st.info(
                    "📊 Trendline unavailable (statsmodels not installed). Run: `pip install statsmodels`"
                )

            fig.update_traces(marker=dict(size=10, color="blue"))
            st.plotly_chart(fig, width="stretch")

            # Calculate trend
            first_5_avg = (
                cost_df.head(5)["cost"].mean() if len(cost_df) >= 5 else cost_df["cost"].mean()
            )
            last_5_avg = cost_df.tail(5)["cost"].mean()
            improvement = ((first_5_avg - last_5_avg) / first_5_avg * 100) if first_5_avg > 0 else 0

            if improvement > 0:
                st.success(
                    f"✅ Cost optimization working! Average cost decreased by {improvement:.1f}% from first 5 to last 5 resumes."
                )
            elif improvement < -10:
                st.warning(
                    "⚠️ Costs increasing. This may indicate more complex JDs or different patterns."
                )
            else:
                st.info(
                    "📊 Cost trend is stable. Continue generating resumes to build pattern library."
                )

        elif len(resume_costs) == 1:
            st.info("Generate at least 2 resumes to see cost trends.")
        else:
            st.info(
                "No resume generation data yet. Create your first resume to start tracking performance."
            )

    except Exception as exc:
        st.error(f"Failed to load performance trends: {exc}")


# ════════════════════════════════════════════════════════════════════
# Tab 2: Salary & Markets (from 8_regional_salary_analytics.py)
# ════════════════════════════════════════════════════════════════════

with tab2:
    st.markdown(
        "AI-powered market intelligence using Claude Opus 4.6 for comprehensive salary analysis"
    )

    # Warning about cost
    st.info(
        "⚠️ **Cost Notice**: This feature uses Claude Opus 4.6 for deep analysis. "
        "Cost: ~$0.15-0.30 per analysis. Use for strategic decisions and negotiations."
    )

    # --- Load Applications ---
    apps = _cached_list_applications_analytics()

    # Show data availability summary
    total_apps = len(apps)
    apps_with_salary = [
        a for a in apps if a.get("salary_min") or a.get("salary_max") or a.get("salary_range")
    ]
    apps_with_location = [a for a in apps if a.get("location")]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Applications", total_apps)
    with col2:
        st.metric("With Salary Data", len(apps_with_salary))
    with col3:
        st.metric("With Location Data", len(apps_with_location))

    if not apps_with_salary:
        st.warning(
            "⚠️ No salary data found. Add salary information to applications in the Tracker to enable analysis."
        )
        st.info(
            "💡 **How to add salary data**: Go to Tracker → Edit the salary columns (Min/Max/Currency) for each application."
        )
    else:
        # Convert to DataFrame for analysis
        df = pd.DataFrame(apps_with_salary)

        # Warn if some apps lack location data
        if "location" not in df.columns or df["location"].isna().all():
            st.warning(
                "⚠️ No location data found. Add location information to applications to enable regional analysis."
            )
            st.info(
                "💡 **How to add location data**: Go to Tracker → Edit the Location column for each application."
            )
        else:
            apps_with_location_and_salary = df[df["location"].notna()]
            if len(apps_with_location_and_salary) < len(df):
                missing_count = len(df) - len(apps_with_location_and_salary)
                st.warning(
                    f"⚠️ {missing_count} application(s) with salary data are missing location information and won't appear in regional analysis."
                )

            # --- Sidebar: Analysis Configuration ---
            st.sidebar.header("Analysis Configuration")

            analysis_type = st.sidebar.selectbox(
                "Analysis Type",
                [
                    "Regional Comparison",
                    "Market Trends",
                    "Cost of Living Adjustment",
                    "Negotiation Strategy",
                    "Custom Query",
                ],
            )

            target_locations = st.sidebar.multiselect(
                "Target Locations",
                options=sorted(df["location"].dropna().unique()),
                default=list(df["location"].dropna().unique()),  # Show ALL locations by default
                help="All locations selected by default. Uncheck to filter.",
            )

            target_roles = st.sidebar.multiselect(
                "Target Roles",
                options=sorted(df["role_title"].dropna().unique()),
                help="Leave empty for all roles",
            )

            # Filter data
            filtered_df = df.copy()
            if target_locations:
                filtered_df = filtered_df[filtered_df["location"].isin(target_locations)]
            if target_roles:
                filtered_df = filtered_df[filtered_df["role_title"].isin(target_roles)]

            if filtered_df.empty:
                st.warning("No data matches the selected filters.")
            else:
                # --- Display Current Data ---
                st.subheader("Current Salary Data")
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("Applications", len(filtered_df))
                with col2:
                    avg_min = filtered_df["salary_min"].dropna().mean()
                    st.metric(
                        "Avg Min Salary",
                        f"${avg_min:,.0f}" if not pd.isna(avg_min) else "N/A",
                    )
                with col3:
                    avg_max = filtered_df["salary_max"].dropna().mean()
                    st.metric(
                        "Avg Max Salary",
                        f"${avg_max:,.0f}" if not pd.isna(avg_max) else "N/A",
                    )
                with col4:
                    locations_count = filtered_df["location"].nunique()
                    st.metric("Locations", locations_count)

                # --- Visualization ---
                st.subheader("Salary Distribution by Location")

                # Create box plot
                fig = px.box(
                    filtered_df,
                    x="location",
                    y=["salary_min", "salary_max"],
                    title="Salary Ranges by Location",
                    labels={
                        "value": "Salary (USD)",
                        "location": "Location",
                        "variable": "Salary Type",
                    },
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)

                # --- AI-Powered Analysis (Opus 4.6) ---
                st.subheader(f"AI Analysis: {analysis_type}")

                if st.button("🚀 Generate Analysis (Opus 4.6)", type="primary"):
                    with st.spinner(
                        "Analyzing market data with Claude Opus 4.6... (this may take 10-20s)"
                    ):
                        # Prepare context for Opus
                        context_data = filtered_df[
                            [
                                "role_title",
                                "company_name",
                                "location",
                                "salary_min",
                                "salary_max",
                                "salary_currency",
                            ]
                        ].to_dict(orient="records")

                        # Build prompt based on analysis type
                        if analysis_type == "Regional Comparison":
                            prompt = f"""Analyze the salary data across {len(target_locations)} locations for product/UX leadership roles.

**Data:** {len(filtered_df)} applications across {locations_count} locations.

**Locations:** {', '.join(target_locations) if target_locations else 'All'}

**Salary Summary:**
- Avg Min: ${avg_min:,.0f}
- Avg Max: ${avg_max:,.0f}

**Raw Data:**
{context_data}

**Analysis Required:**
1. Compare salary ranges across regions
2. Identify highest/lowest paying markets
3. Explain regional salary differences (cost of living, market demand, industry hubs)
4. Recommend optimal target locations for maximum compensation
5. Provide negotiation insights per region

Format as a clear, actionable report with specific numbers and recommendations."""

                        elif analysis_type == "Market Trends":
                            prompt = f"""Analyze market trends and demand indicators from this salary dataset.

**Data:** {len(filtered_df)} applications
**Roles:** {', '.join(target_roles) if target_roles else 'Multiple'}
**Locations:** {', '.join(target_locations) if target_locations else 'All'}

**Raw Data:**
{context_data}

**Analysis Required:**
1. Identify salary trends and patterns
2. Assess market demand by role/location
3. Compare against known industry benchmarks (cite sources if possible)
4. Predict where compensation is heading
5. Recommend timing strategies (best time to negotiate, market cycles)

Provide data-driven insights with specific numbers."""

                        elif analysis_type == "Cost of Living Adjustment":
                            prompt = f"""Perform cost of living adjustments for these salary offers.

**Data:** {len(filtered_df)} applications across {locations_count} locations

**Raw Data:**
{context_data}

**Analysis Required:**
1. Apply cost of living adjustments for each location
2. Calculate "real" salary (purchasing power) for each offer
3. Rank offers by adjusted compensation
4. Identify best value locations (high salary + low cost of living)
5. Provide specific adjustment factors used

Use recent cost of living data (2024-2026) and cite sources."""

                        elif analysis_type == "Negotiation Strategy":
                            prompt = f"""Develop negotiation strategies for these opportunities.

**Data:** {len(filtered_df)} applications
**Target Locations:** {', '.join(target_locations) if target_locations else 'All'}
**Target Roles:** {', '.join(target_roles) if target_roles else 'All'}

**Raw Data:**
{context_data}

**Analysis Required:**
1. Identify negotiation leverage points per location/role
2. Recommend target salary ranges to request
3. Provide market-based justification for higher offers
4. Script negotiation talking points
5. Identify red flags or lowball offers

Be specific and actionable."""

                        else:  # Custom Query
                            custom_query = st.text_area(
                                "Custom Analysis Query",
                                placeholder="E.g., 'Compare remote vs on-site salary premiums across these roles'",
                            )
                            if not custom_query:
                                st.warning("Please enter a custom query above.")
                                st.stop()

                            prompt = f"""Analyze this salary dataset based on the following custom query:

**Query:** {custom_query}

**Data:** {len(filtered_df)} applications
**Locations:** {', '.join(target_locations) if target_locations else 'All'}
**Roles:** {', '.join(target_roles) if target_roles else 'Multiple'}

**Raw Data:**
{context_data}

Provide a detailed, data-driven analysis addressing the query."""

                        # Call Opus 4.6 using jSeeker LLM wrapper
                        try:
                            # Set model override to use Opus 4.6
                            llm.model_override = "opus"

                            # Call with the prompt (cost tracking happens automatically)
                            analysis = llm.call(
                                prompt=prompt,
                                task="regional_salary_analytics",
                                model="opus",
                                temperature=0.3,
                                max_tokens=4000,
                                use_local_cache=False,  # Don't cache expensive analyses
                            )

                            # Display analysis
                            st.markdown("### Analysis Results")
                            st.markdown(analysis)

                            # Get cost info from last call
                            if llm._session_costs:
                                last_cost = llm._session_costs[-1]
                                cost = last_cost.cost_usd
                                input_tokens = last_cost.input_tokens
                                output_tokens = last_cost.output_tokens

                                st.caption(
                                    f"💰 Analysis cost: ${cost:.3f} | "
                                    f"Tokens: {input_tokens:,} in / {output_tokens:,} out | "
                                    f"Model: Claude Opus 4.6"
                                )
                            else:
                                st.caption("💰 Analysis cost: Tracked in API costs table")

                            st.success("✅ Analysis complete! Review insights above.")

                            # Reset model override
                            llm.model_override = None

                        except Exception as e:
                            st.error(f"Analysis failed: {str(e)}")
                            st.info(
                                "Ensure your ANTHROPIC_API_KEY environment variable is set correctly."
                            )

                # --- Export Data ---
                with st.expander("📊 Export Salary Data"):
                    st.caption("Download filtered salary data for external analysis")

                    export_df = filtered_df[
                        [
                            "role_title",
                            "company_name",
                            "location",
                            "salary_min",
                            "salary_max",
                            "salary_currency",
                            "application_status",
                            "created_at",
                        ]
                    ]

                    csv = export_df.to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name="salary_data_export.csv",
                        mime="text/csv",
                    )
