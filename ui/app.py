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
*GAIA Ecosystem Product v0.2.1*
""")
