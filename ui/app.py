"""JSEEKER - The shape-shifting resume engine.

Streamlit entry point and navigation.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging for jseeker modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

import streamlit as st

st.set_page_config(
    page_title="JSEEKER - Resume Engine",
    page_icon="J",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize DB on first load
from jseeker.tracker import init_db

init_db()

st.sidebar.title("JSEEKER")
st.sidebar.caption("The Shape-Shifting Resume Engine")
st.sidebar.markdown("---")

# Session cost display
try:
    from jseeker.llm import llm

    session_cost = llm.get_total_session_cost()
    st.sidebar.metric("Session Cost", f"${session_cost:.3f}")
except Exception:
    pass

# Model selector
st.sidebar.markdown("---")
_model_options = ["Haiku (Fast/Cheap)", "Sonnet (Quality)", "Opus (Premium)"]

# Track previous selection for change detection
_prev_model = st.session_state.get("_prev_model_choice", "Haiku (Fast/Cheap)")
_model_choice = st.sidebar.selectbox("Model", _model_options, index=0)
_model_map = {"Haiku (Fast/Cheap)": None, "Sonnet (Quality)": "sonnet", "Opus (Premium)": "opus"}

try:
    llm.model_override = _model_map[_model_choice]
except NameError:
    pass

# Show confirmation when model changes
if _model_choice != _prev_model:
    st.session_state["_prev_model_choice"] = _model_choice
    if _model_map[_model_choice] == "opus":
        st.sidebar.warning(f"Model: **Opus** — Premium pricing ($15/$75 per M tokens)")
    elif _model_map[_model_choice] == "sonnet":
        st.sidebar.info(f"Model changed to **Sonnet** — Quality mode")
    else:
        st.sidebar.success(f"Model changed to **Haiku** — Fast/Cheap mode")
else:
    st.session_state["_prev_model_choice"] = _model_choice

# Model traceability
try:
    costs = llm.get_session_costs()
    if costs:
        last = costs[-1]
        model_short = last.model.split("-")[1]
        st.sidebar.caption(f"Last: {model_short} · ${last.cost_usd:.4f} · {last.task}")
except Exception:
    pass

st.markdown("""
# JSEEKER
### The Shape-Shifting Resume Engine

Navigate using the sidebar pages:

1. **Dashboard** — Application pipeline, metrics, quick actions
2. **New Resume** — JD paste → adapted resume → export
3. **Resume Library** — Browse and manage generated resumes
4. **Tracker** — Application CRM with 3 status pipelines
5. **Job Discovery** — Tag-based job search across boards

---
*GAIA Ecosystem Product v0.3.6*
""")
