"""Learning Insights — Transparency dashboard for pattern learning and cost optimization."""

import json
import sqlite3
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import settings
from jseeker.pattern_learner import get_pattern_stats

st.set_page_config(page_title="Learning Insights - jSeeker", page_icon="🧠", layout="wide")

st.title("🧠 Learning Insights")
st.markdown(
    "See how jSeeker learns from your feedback and optimizes costs over time. "
    "The system stores adaptation patterns and reuses them, reducing LLM calls and costs."
)

# ── Section 1: Pattern Learning Stats ──────────────────────────────────────

st.markdown("---")
st.header("📊 Pattern Learning Stats")

try:
    stats = get_pattern_stats(db_path=settings.db_path)

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
            pattern_df = pattern_df[
                ["id", "type", "frequency", "confidence", "context", "source", "target"]
            ]
            pattern_df.columns = [
                "ID",
                "Type",
                "Uses",
                "Confidence",
                "JD Context",
                "Source Text",
                "Target Text",
            ]

            st.dataframe(
                pattern_df,
                width="stretch",
                hide_index=True,
            )

except Exception as exc:
    st.error(f"Failed to load pattern stats: {exc}")


# ── Section 2: Cost Optimization ───────────────────────────────────────────

st.markdown("---")
st.header("💰 Cost Optimization")

try:
    conn = sqlite3.connect(str(settings.db_path))
    c = conn.cursor()

    # Monthly cost
    c.execute("""
        SELECT COALESCE(SUM(cost_usd), 0) as total
        FROM api_costs
        WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')
    """)
    monthly_cost = c.fetchone()[0]

    # Total resumes generated
    c.execute("SELECT COUNT(*) FROM resumes")
    total_resumes = c.fetchone()[0]

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

    # Cumulative cost chart
    c.execute("""
        SELECT DATE(timestamp) as date, SUM(cost_usd) as daily_cost
        FROM api_costs
        GROUP BY DATE(timestamp)
        ORDER BY timestamp ASC
    """)
    cost_data = [{"date": row[0], "cost": row[1]} for row in c.fetchall()]

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

    conn.close()

except Exception as exc:
    st.error(f"Failed to load cost data: {exc}")


# ── Section 3: JSON Rules & Schema ─────────────────────────────────────────

st.markdown("---")
st.header("📋 Pattern Schema & JSON Rules")

st.markdown("""
jSeeker stores learned patterns in a SQLite database. Each pattern represents a transformation
that worked well in the past (e.g., how to adapt a specific bullet point for a specific role).
""")

schema_example = {
    "id": 42,
    "pattern_type": "bullet_adaptation",
    "source_text": "Led cross-functional teams to deliver products",
    "target_text": "Directed 12-person cross-functional team to ship 3 AI-powered products in 9 months",
    "jd_context": {
        "role": "senior product manager",
        "keywords": ["product management", "cross-functional", "ai", "agile"],
        "industry": "technology",
    },
    "frequency": 5,
    "confidence": 0.95,
}

st.markdown("### Example Pattern (JSON)")
st.json(schema_example, expanded=True)

st.markdown("""
**Field Explanations**:
- `pattern_type`: Category of adaptation (bullet, summary, skills, etc.)
- `source_text`: Original text from resume block
- `target_text`: Adapted text (user-edited or LLM-generated)
- `jd_context`: Job description context (role, keywords, industry)
- `frequency`: Number of times this pattern was successfully reused
- `confidence`: Trust score (0.0-1.0) based on context similarity
""")


# ── Section 4: Pattern History ────────────────────────────────────────────

st.markdown("---")
st.header("🔄 Pattern History")

st.markdown("""
Track how patterns evolve and improve over time. Patterns start with low frequency and confidence,
then increase as they are validated by successful reuse.
""")

try:
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get all patterns ordered by creation date
    c.execute("""
        SELECT id, pattern_type, source_text, target_text, jd_context,
               frequency, confidence, created_at, last_used_at
        FROM learned_patterns
        ORDER BY created_at DESC
        LIMIT 50
    """)

    patterns = c.fetchall()

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
                    except Exception:
                        role = "N/A"
                        keywords = "N/A"

                    # Display pattern details
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.markdown(f"**Pattern #{pattern['id']}** — {role}")
                        st.markdown(f"**Keywords**: {keywords if keywords else 'None'}")

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
                        created = datetime.fromisoformat(pattern["created_at"]).strftime("%b %d")
                        last_used = datetime.fromisoformat(pattern["last_used_at"]).strftime(
                            "%b %d"
                        )

                        st.caption(f"Created: {created}")
                        st.caption(f"Last used: {last_used}")

                    st.markdown("---")

        # Pattern frequency over time chart
        st.markdown("### Pattern Usage Over Time")

        c.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as patterns_created
            FROM learned_patterns
            GROUP BY DATE(created_at)
            ORDER BY created_at ASC
        """)
        pattern_timeline = [{"date": row[0], "count": row[1]} for row in c.fetchall()]

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

        c.execute("""
            SELECT pattern_type,
                   COUNT(*) as pattern_count,
                   SUM(frequency) as total_uses,
                   SUM(CASE WHEN frequency >= 3 THEN frequency ELSE 0 END) as cache_hits
            FROM learned_patterns
            GROUP BY pattern_type
            ORDER BY cache_hits DESC
        """)

        savings_data = []
        for row in c.fetchall():
            cost_saved = row["cache_hits"] * 0.01  # $0.01 per cache hit
            savings_data.append(
                {
                    "Type": row["pattern_type"].replace("_", " ").title(),
                    "Patterns": row["pattern_count"],
                    "Total Uses": row["total_uses"],
                    "Cache Hits": row["cache_hits"],
                    "Cost Saved": f"${cost_saved:.2f}",
                }
            )

        if savings_data:
            savings_df = pd.DataFrame(savings_data)
            st.dataframe(
                savings_df,
                width="stretch",
                hide_index=True,
            )

            total_saved = sum([float(row["Cost Saved"].replace("$", "")) for row in savings_data])
            st.success(f"💰 Total saved from pattern reuse: **${total_saved:.2f}**")

    else:
        st.info(
            "No patterns learned yet. Generate a few resumes and the system will start learning adaptation patterns."
        )

    conn.close()

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
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get cost per resume over time
    c.execute("""
        SELECT
            ROW_NUMBER() OVER (ORDER BY created_at) as resume_number,
            generation_cost
        FROM resumes
        WHERE generation_cost IS NOT NULL AND generation_cost > 0
        ORDER BY created_at ASC
    """)

    resume_costs = [{"resume_number": row[0], "cost": row[1]} for row in c.fetchall()]

    if len(resume_costs) >= 2:
        cost_df = pd.DataFrame(resume_costs)

        # Try to add trendline if statsmodels is available
        try:
            fig = px.scatter(
                cost_df,
                x="resume_number",
                y="cost",
                title="Cost per Resume Over Time (Should Decrease)",
                labels={"resume_number": "Resume Number", "cost": "Generation Cost ($)"},
                trendline="lowess",
            )
        except Exception:
            # Fallback: simple scatter plot without trendline
            fig = px.scatter(
                cost_df,
                x="resume_number",
                y="cost",
                title="Cost per Resume Over Time (Should Decrease)",
                labels={"resume_number": "Resume Number", "cost": "Generation Cost ($)"},
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

    conn.close()

except Exception as exc:
    st.error(f"Failed to load performance trends: {exc}")


# ── Footer ──────────────────────────────────────────────────────────────────

st.markdown("---")
st.caption(
    "💡 **Tip**: The more resumes you generate, the smarter jSeeker becomes and the less each resume costs."
)
