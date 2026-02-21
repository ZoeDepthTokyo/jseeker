"""jSeeker Launch Script (Default).

Forwards to launch_jseeker.py. This is the default entry point for jSeeker.

For other launch options:
  - python launch_jseeker.py  (same as this, explicit)
  - python launch_argus.py    (ARGUS only on port 8501)
  - python launch_both.py     (both jSeeker + ARGUS together)
  - python run.py             (full pipeline launcher with venv/dep checks)

Usage:
    python launch.py
    python launch.py --debug
    python launch.py --check-only
"""

from pathlib import Path

if __name__ == "__main__":
    # Import and delegate to launch_jseeker so all args pass through cleanly
    _launcher_path = Path(__file__).parent / "launch_jseeker.py"
    _ns: dict = {}
    exec(compile(_launcher_path.read_text(), str(_launcher_path), "exec"), _ns)
    _ns["launcher"].run()
