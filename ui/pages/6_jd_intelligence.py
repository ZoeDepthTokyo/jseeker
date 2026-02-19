"""JD Intelligence -- aggregate patterns across all parsed job descriptions."""

import json
import sqlite3
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="JD Intelligence", page_icon="Brain", layout="wide")
st.title("JD Intelligence")
st.caption("Insights synthesized from every job description you've ever analyzed.")

from jseeker.tracker import tracker_db
from jseeker.intelligence import (
    aggregate_jd_corpus,
    generate_ideal_candidate_brief,
    export_profile_docx,
)

# -- Load aggregate (cached in session) -------------------------------------
if "jd_aggregate" not in st.session_state:
    with st.spinner("Analyzing your JD corpus..."):
        st.session_state["jd_aggregate"] = aggregate_jd_corpus()

agg = st.session_state["jd_aggregate"]

if agg["total_jds"] == 0:
    st.info(
        "No parsed JDs found yet. Use the **New Resume** page to parse job descriptions "
        "-- this page will populate as you analyze more roles."
    )
    st.stop()

# -- Tabs -------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["Market Signals", "Ideal Candidate", "Salary Sweet Spot"])

with tab1:
    st.subheader(f"Corpus: {agg['total_jds']} parsed JDs")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total JDs Analyzed", agg["total_jds"])
    col2.metric("Markets Represented", len(agg.get("markets", [])))
    col3.metric("Unique Keywords Tracked", len(agg.get("top_keywords", [])))

    st.markdown("---")

    # Top keywords bar chart
    if agg["top_keywords"]:
        st.subheader("Most Demanded Keywords")
        import pandas as pd

        kw_df = pd.DataFrame(agg["top_keywords"][:20], columns=["Keyword", "Frequency"])
        st.bar_chart(kw_df.set_index("Keyword"))

    col_a, col_b = st.columns(2)
    with col_a:
        if agg.get("remote_policy_breakdown"):
            st.subheader("Remote Policy")
            for policy, count in agg["remote_policy_breakdown"].items():
                st.write(f"**{policy.title()}**: {count} roles")

    with col_b:
        if agg.get("experience_distribution"):
            st.subheader("Experience Requirements")
            for exp, count in agg["experience_distribution"].items():
                st.write(f"**{exp}**: {count} roles")

    if agg.get("culture_signals"):
        st.markdown("---")
        st.subheader("Culture Signals (across all JDs)")
        signals_text = " · ".join(f"{sig} ({cnt})" for sig, cnt in agg["culture_signals"][:12])
        st.markdown(signals_text)

with tab2:
    st.subheader("Generate Ideal Candidate Profile")
    st.caption(
        "Select a JD you've parsed, then run the analysis to see where you stand "
        "vs. the ideal match."
    )

    # Load JD list from jd_cache
    db = tracker_db.db_path
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    jd_rows = conn.execute(
        "SELECT pruned_text_hash, title, company, created_at "
        "FROM jd_cache ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()

    if not jd_rows:
        st.info("No cached JDs. Parse a job description in New Resume first.")
    else:
        jd_options = {
            f"{r['title'] or 'Unknown'} @ {r['company'] or 'Unknown'} "
            f"({(r['created_at'] or '')[:10]})": r["pruned_text_hash"]
            for r in jd_rows
        }
        selected_label = st.selectbox(
            "Select a JD:", list(jd_options.keys()), key="intel_jd_select"
        )
        selected_hash = jd_options[selected_label]

        if st.button("Run Analysis", key="run_intel", type="primary"):
            st.session_state.pop("intel_report", None)
            with st.spinner("Analyzing... (~15 seconds, costs ~$0.015)"):
                try:
                    # Load ParsedJD from cache
                    conn = sqlite3.connect(str(db))
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT parsed_json FROM jd_cache WHERE pruned_text_hash = ?",
                        (selected_hash,),
                    ).fetchone()
                    conn.close()

                    from jseeker.models import ParsedJD, AdaptedResume

                    parsed_jd = ParsedJD(**json.loads(row["parsed_json"]))

                    # Use empty AdaptedResume if no pipeline has been run
                    adapted = st.session_state.get("pipeline_result")
                    if adapted and hasattr(adapted, "adapted_resume"):
                        adapted_resume = adapted.adapted_resume
                    else:
                        adapted_resume = AdaptedResume()

                    report = generate_ideal_candidate_brief(parsed_jd, adapted_resume, agg)
                    st.session_state["intel_report"] = report
                    st.session_state["intel_parsed_jd"] = parsed_jd
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

        if st.session_state.get("intel_report"):
            report = st.session_state["intel_report"]

            st.markdown("---")
            col_left, col_right = st.columns([6, 4])

            with col_left:
                st.subheader("Ideal Candidate Profile")
                st.markdown(report.ideal_profile)

                if report.strengths:
                    with st.expander("Your Strengths", expanded=True):
                        for s in report.strengths:
                            st.success(s)

                if report.gaps:
                    with st.expander("Gaps to Address", expanded=True):
                        for g in report.gaps:
                            st.warning(g)

            with col_right:
                st.metric("Keyword Coverage", f"{report.keyword_coverage:.0%}")
                if report.salary_angle:
                    st.subheader("Salary Angle")
                    st.info(report.salary_angle)

                # DOCX export
                if st.button("Export Profile as DOCX", key="export_intel_docx"):
                    out_path = Path("output") / "jd_intelligence_profile.docx"
                    with st.spinner("Generating DOCX..."):
                        export_profile_docx(report, out_path)
                    with open(out_path, "rb") as f:
                        st.download_button(
                            "Download DOCX",
                            f.read(),
                            file_name="ideal_candidate_profile.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key="dl_intel_docx",
                        )

with tab3:
    st.subheader("Salary Sweet Spot")
    global_perc = agg.get("salary_percentiles", {})
    by_market = agg.get("salary_by_market", {})

    if not global_perc:
        st.info("No salary data yet. Applications with salary ranges will populate this view.")
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Global P25",
            f"${global_perc.get('p25', 0):,}" if global_perc.get("p25") else "N/A",
        )
        col2.metric(
            "Global Median",
            f"${global_perc.get('p50', 0):,}" if global_perc.get("p50") else "N/A",
        )
        col3.metric(
            "Global P75",
            f"${global_perc.get('p75', 0):,}" if global_perc.get("p75") else "N/A",
        )

        if by_market:
            st.markdown("---")
            st.subheader("By Market")
            import pandas as pd

            market_rows = []
            for market, perc in by_market.items():
                market_rows.append(
                    {
                        "Market": market.upper(),
                        "P25": f"${perc.get('p25', 0):,}" if perc.get("p25") else "N/A",
                        "Median": (f"${perc.get('p50', 0):,}" if perc.get("p50") else "N/A"),
                        "P75": f"${perc.get('p75', 0):,}" if perc.get("p75") else "N/A",
                        "Data Points": perc.get("count", 0),
                    }
                )
            st.dataframe(pd.DataFrame(market_rows), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Negotiation Recommendation")
        if global_perc.get("p75"):
            st.success(
                f"**Ask for ${global_perc['p75']:,}** "
                f"(P75 across {global_perc.get('count', 0)} data points). "
                "Negotiate from strength -- this is the upper quartile, not the ceiling."
            )
        st.caption("For deeper regional analysis, visit the **Analytics** tab.")
