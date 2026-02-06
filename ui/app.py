"""PROTEUS — The Shape-Shifting Resume Engine.

Streamlit entry point and navigation.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st

st.set_page_config(
    page_title="PROTEUS — Resume Engine",
    page_icon="P",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize DB on first load
from proteus.tracker import init_db
init_db()

st.sidebar.title("PROTEUS")
st.sidebar.caption("The Shape-Shifting Resume Engine")
st.sidebar.markdown("---")

st.markdown("""
# PROTEUS
### The Shape-Shifting Resume Engine

Navigate using the sidebar pages:

1. **Dashboard** — Application pipeline, metrics, quick actions
2. **New Resume** — JD paste → adapted resume → export
3. **Tracker** — Application CRM with 3 status pipelines
4. **Job Discovery** — Tag-based job search across boards

---
*GAIA Ecosystem Component v0.1.0*
""")
