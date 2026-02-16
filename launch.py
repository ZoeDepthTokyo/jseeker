"""jSeeker Launch Script (Default).

This is the default launcher for jSeeker. It starts only jSeeker on port 8502.

For other launch options:
  - python launch_jseeker.py  (same as this, explicit)
  - python launch_argus.py    (ARGUS only on port 8501)
  - python launch_both.py     (both jSeeker + ARGUS together)

Usage:
    python launch.py
"""

# Forward to standalone jSeeker launcher
if __name__ == "__main__":
    from pathlib import Path

    # Import and execute launch_jseeker
    launch_jseeker_path = Path(__file__).parent / "launch_jseeker.py"

    with open(launch_jseeker_path) as f:
        code = compile(f.read(), str(launch_jseeker_path), "exec")
        exec(code)
