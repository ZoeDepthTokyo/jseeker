"""Learning Insights — Transparency dashboard for pattern learning and cost optimization."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

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
        st.info("No patterns learned yet. Generate a few resumes to start building the pattern library.")
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
            pattern_df = pattern_df[["id", "type", "frequency", "confidence", "context", "source", "target"]]
            pattern_df.columns = ["ID", "Type", "Uses", "Confidence", "Learned from Role", "Source Text", "Target Text"]

            st.dataframe(
                pattern_df,
                width="stretch",
                hide_index=True,
            )

            st.caption(
                "💡 **Note**: 'Learned from Role' shows the job description that triggered this pattern. "
                "Your resume content (UX/Product experience) was adapted for these roles."
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

# Load real pattern data from database
try:
    conn_schema = sqlite3.connect(str(settings.db_path))
    conn_schema.row_factory = sqlite3.Row
    c_schema = conn_schema.cursor()

    c_schema.execute("""
        SELECT id, pattern_type, source_text, target_text, jd_context, frequency, confidence
        FROM learned_patterns
        ORDER BY frequency DESC
        LIMIT 1
    """)

    real_pattern = c_schema.fetchone()
    conn_schema.close()

    if real_pattern:
        context_data = json.loads(real_pattern["jd_context"] or "{}")
        schema_example = {
            "id": real_pattern["id"],
            "pattern_type": real_pattern["pattern_type"],
            "source_text": real_pattern["source_text"][:150] + ("..." if len(real_pattern["source_text"]) > 150 else ""),
            "target_text": real_pattern["target_text"][:150] + ("..." if len(real_pattern["target_text"]) > 150 else ""),
            "jd_context": context_data,
            "frequency": real_pattern["frequency"],
            "confidence": real_pattern["confidence"],
        }

        st.markdown("### Real Pattern Example (JSON)")
        st.caption("This is an actual pattern learned from your resume generation history:")
        st.json(schema_example, expanded=True)

    else:
        # Fallback to example if no patterns exist
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
        st.caption("No patterns learned yet. This is a sample structure:")
        st.json(schema_example, expanded=True)

except Exception as e:
    st.warning(f"Could not load real pattern data: {e}")

# Show actual skill tags from resume blocks
st.markdown("### Your Resume Skills (Available for Adaptation)")
try:
    import yaml
    skills_path = Path(__file__).parent.parent.parent / "data" / "resume_blocks" / "skills.yaml"

    if skills_path.exists():
        with open(skills_path, 'r', encoding='utf-8') as f:
            skills_data = yaml.safe_load(f)

        # Extract skill categories and items
        skill_categories = []
        for category_key, category_data in skills_data.get("skills", {}).items():
            category_name = category_data.get("display_name", category_key)
            skill_items = [item["name"] for item in category_data.get("items", [])]
            skill_categories.append({
                "Category": category_name,
                "Skills": ", ".join(skill_items[:3]) + ("..." if len(skill_items) > 3 else ""),
                "Total": len(skill_items)
            })

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
            with st.expander(f"**{ptype.replace('_', ' ').title()}** ({len(type_patterns)} patterns)", expanded=False):
                for pattern in type_patterns:
                    # Parse JD context
                    try:
                        context = json.loads(pattern["jd_context"] or "{}")
                        role = context.get("role", "N/A")
                        keywords = ", ".join(context.get("keywords", [])[:5])
                    except:
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
                        st.code(pattern["source_text"][:200] + ("..." if len(pattern["source_text"]) > 200 else ""), language="text")

                        st.markdown("**After:**")
                        st.code(pattern["target_text"][:200] + ("..." if len(pattern["target_text"]) > 200 else ""), language="text")

                    with col2:
                        st.metric("Used", f"{pattern['frequency']}x")
                        st.metric("Confidence", f"{pattern['confidence']:.2f}")

                        # Format dates
                        created = datetime.fromisoformat(pattern["created_at"]).strftime("%b %d")
                        last_used = datetime.fromisoformat(pattern["last_used_at"]).strftime("%b %d")

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
            fig.add_trace(go.Scatter(
                x=timeline_df["date"],
                y=timeline_df["cumulative"],
                mode="lines+markers",
                name="Total Patterns",
                line=dict(color="blue", width=2),
            ))

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
            savings_data.append({
                "Type": row["pattern_type"].replace("_", " ").title(),
                "Patterns": row["pattern_count"],
                "Total Uses": row["total_uses"],
                "Cache Hits": row["cache_hits"],
                "Cost Saved": f"${cost_saved:.2f}",
            })

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
        st.info("No patterns learned yet. Generate a few resumes and the system will start learning adaptation patterns.")

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
            st.info("📊 Trendline unavailable (statsmodels not installed). Run: `pip install statsmodels`")

        fig.update_traces(marker=dict(size=10, color="blue"))
        st.plotly_chart(fig, width="stretch")

        # Calculate trend
        first_5_avg = cost_df.head(5)["cost"].mean() if len(cost_df) >= 5 else cost_df["cost"].mean()
        last_5_avg = cost_df.tail(5)["cost"].mean()
        improvement = ((first_5_avg - last_5_avg) / first_5_avg * 100) if first_5_avg > 0 else 0

        if improvement > 0:
            st.success(f"✅ Cost optimization working! Average cost decreased by {improvement:.1f}% from first 5 to last 5 resumes.")
        elif improvement < -10:
            st.warning("⚠️ Costs increasing. This may indicate more complex JDs or different patterns.")
        else:
            st.info("📊 Cost trend is stable. Continue generating resumes to build pattern library.")

    elif len(resume_costs) == 1:
        st.info("Generate at least 2 resumes to see cost trends.")
    else:
        st.info("No resume generation data yet. Create your first resume to start tracking performance.")

    conn.close()

except Exception as exc:
    st.error(f"Failed to load performance trends: {exc}")


# ── Section 6: Regional Salary Analytics ──────────────────────────────────

st.markdown("---")
st.header("🌍 Regional Salary Analytics")

st.markdown("""
Compare salary ranges across different geographic regions to understand market rates.
""")

def normalize_location_to_region(location: str) -> str:
    """Map location string to standardized region."""
    if not location:
        return "Unknown"

    loc_lower = location.lower()

    # United States
    if any(term in loc_lower for term in ["united states", "us", "usa", "california", "new york", "texas", "massachusetts", "illinois", "minnesota", "virginia", "washington", "oregon", "florida", "georgia", "colorado", "atlanta", "boston", "chicago", "dallas", "denver", "detroit", "houston", "los angeles", "mclean", "new york", "hoboken", "philadelphia", "san francisco", "seattle", "san diego", "santa monica", "acton", "frisco", "eagan"]):
        return "United States"

    # Canada
    if any(term in loc_lower for term in ["canada", "toronto", "ontario", "vancouver", "montreal", "calgary"]):
        return "Canada"

    # Mexico
    if any(term in loc_lower for term in ["mexico", "méxico", "mx", "ciudad de mexico", "monterrey", "guadalajara"]):
        return "Mexico"

    # UK
    if any(term in loc_lower for term in ["uk", "united kingdom", "london", "manchester", "edinburgh", "bristol"]):
        return "United Kingdom"

    # EU
    if any(term in loc_lower for term in ["germany", "france", "spain", "italy", "netherlands", "sweden", "denmark", "norway", "berlin", "paris", "madrid", "amsterdam", "copenhagen", "stockholm"]):
        return "Europe"

    # LATAM (excluding Mexico)
    if any(term in loc_lower for term in ["brazil", "argentina", "chile", "colombia", "peru", "buenos aires", "santiago", "bogota", "lima", "são paulo"]):
        return "Latin America"

    # Asia
    if any(term in loc_lower for term in ["china", "japan", "india", "singapore", "korea", "tokyo", "beijing", "shanghai", "bangalore", "seoul"]):
        return "Asia"

    # Remote (if explicitly stated)
    if "remote" in loc_lower:
        return "Remote (Global)"

    return "Other"

try:
    conn_salary = sqlite3.connect(str(settings.db_path))
    conn_salary.row_factory = sqlite3.Row
    c_salary = conn_salary.cursor()

    # Get all applications with salary data
    c_salary.execute("""
        SELECT location, salary_min, salary_max, salary_currency
        FROM applications
        WHERE salary_min IS NOT NULL AND salary_max IS NOT NULL
    """)

    salary_data = []
    for row in c_salary.fetchall():
        location = row["location"] or "Unknown"
        region = normalize_location_to_region(location)
        avg_salary = (row["salary_min"] + row["salary_max"]) / 2.0

        # Convert to USD if needed (simple approximation)
        currency = row["salary_currency"] or "USD"
        if currency != "USD":
            # Exchange rate approximations (as of 2026)
            rates = {"EUR": 1.1, "GBP": 1.25, "CAD": 0.75, "MXN": 0.05, "INR": 0.012}
            avg_salary *= rates.get(currency, 1.0)

        salary_data.append({
            "region": region,
            "salary": avg_salary,
            "location": location,
        })

    conn_salary.close()

    if len(salary_data) >= 2:
        # Aggregate by region
        salary_df = pd.DataFrame(salary_data)
        regional_stats = salary_df.groupby("region").agg({
            "salary": ["mean", "count", "min", "max"]
        }).reset_index()

        regional_stats.columns = ["Region", "Avg Salary", "Job Count", "Min Salary", "Max Salary"]
        regional_stats = regional_stats[regional_stats["Job Count"] >= 1].sort_values("Avg Salary", ascending=False)

        if len(regional_stats) > 0:
            col1, col2 = st.columns(2)

            with col1:
                # Bar chart
                fig_bar = px.bar(
                    regional_stats,
                    x="Region",
                    y="Avg Salary",
                    title="Average Salary by Region",
                    labels={"Avg Salary": "Average Salary (USD)", "Region": "Region"},
                    color="Avg Salary",
                    color_continuous_scale="Viridis",
                )
                fig_bar.update_traces(text=regional_stats["Job Count"].apply(lambda x: f"{x} jobs"), textposition="outside")
                st.plotly_chart(fig_bar, use_container_width=True)

            with col2:
                # Radar/Spider chart (only if 3+ regions)
                if len(regional_stats) >= 3:
                    fig_radar = go.Figure()

                    fig_radar.add_trace(go.Scatterpolar(
                        r=regional_stats["Avg Salary"],
                        theta=regional_stats["Region"],
                        fill='toself',
                        name='Average Salary',
                        line=dict(color='blue')
                    ))

                    fig_radar.update_layout(
                        polar=dict(
                            radialaxis=dict(
                                visible=True,
                                range=[0, regional_stats["Avg Salary"].max() * 1.1]
                            )
                        ),
                        showlegend=False,
                        title="Regional Salary Distribution (Radar)"
                    )

                    st.plotly_chart(fig_radar, use_container_width=True)
                else:
                    st.info("Add more jobs from different regions to see radar chart (need 3+ regions).")

            # Data table
            st.markdown("### Regional Salary Summary")
            display_df = regional_stats.copy()
            display_df["Avg Salary"] = display_df["Avg Salary"].apply(lambda x: f"${x:,.0f}")
            display_df["Min Salary"] = display_df["Min Salary"].apply(lambda x: f"${x:,.0f}")
            display_df["Max Salary"] = display_df["Max Salary"].apply(lambda x: f"${x:,.0f}")

            st.dataframe(
                display_df,
                width="stretch",
                hide_index=True,
            )

            # Insights
            highest_region = regional_stats.iloc[0]["Region"]
            highest_salary = regional_stats.iloc[0]["Avg Salary"]
            st.success(f"💰 Highest average salary: **{highest_region}** at **${highest_salary:,.0f}** ({int(regional_stats.iloc[0]['Job Count'])} jobs)")

        else:
            st.info("Not enough regional data yet. Add more jobs from different locations to see regional comparison.")

    elif len(salary_data) == 1:
        st.info("Only 1 job with salary data. Add more jobs to see regional comparison.")
    else:
        st.info("No salary data available yet. Job discovery will populate salary ranges when available.")

except Exception as exc:
    st.error(f"Failed to load regional salary analytics: {exc}")


# ── Footer ──────────────────────────────────────────────────────────────────

st.markdown("---")
st.caption("💡 **Tip**: The more resumes you generate, the smarter jSeeker becomes and the less each resume costs.")
