"""Regional Salary Analytics - Market Intelligence Dashboard.

Provides AI-powered salary analysis using Opus 4.6 for deep market insights:
- Regional salary ranges and trends
- Cost of living adjustments
- Market demand indicators
- Compensation benchmarking
- Negotiation guidance

NOTE: This feature uses Claude Opus 4.6 for comprehensive analysis.
Cost: ~$0.15-0.30 per analysis (higher quality, deeper insights).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from jseeker.llm import llm
from jseeker.tracker import tracker_db

st.set_page_config(page_title="Regional Salary Analytics", page_icon="💰", layout="wide")

st.title("💰 Regional Salary Analytics")
st.caption("AI-powered market intelligence using Claude Opus 4.6 for comprehensive salary analysis")

# Warning about cost
st.info(
    "⚠️ **Cost Notice**: This feature uses Claude Opus 4.6 for deep analysis. "
    "Cost: ~$0.15-0.30 per analysis. Use for strategic decisions and negotiations."
)

# --- Load Applications ---
apps = tracker_db.list_applications()

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
    st.stop()

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
    st.stop()

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
    st.stop()

# --- Display Current Data ---
st.subheader("Current Salary Data")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Applications", len(filtered_df))
with col2:
    avg_min = filtered_df["salary_min"].dropna().mean()
    st.metric("Avg Min Salary", f"${avg_min:,.0f}" if not pd.isna(avg_min) else "N/A")
with col3:
    avg_max = filtered_df["salary_max"].dropna().mean()
    st.metric("Avg Max Salary", f"${avg_max:,.0f}" if not pd.isna(avg_max) else "N/A")
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
    labels={"value": "Salary (USD)", "location": "Location", "variable": "Salary Type"},
)
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)

# --- AI-Powered Analysis (Opus 4.6) ---
st.subheader(f"AI Analysis: {analysis_type}")

if st.button("🚀 Generate Analysis (Opus 4.6)", type="primary"):
    with st.spinner("Analyzing market data with Claude Opus 4.6... (this may take 10-20s)"):
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
            st.info("Ensure your ANTHROPIC_API_KEY environment variable is set correctly.")

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
