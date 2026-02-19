"""jSeeker Launch Script (Standalone).

Starts jSeeker (Streamlit Resume Engine) on port 8502.
Uses the shared gaia_launch_lib for standardized launch infrastructure.

Usage:
    python launch_jseeker.py
    python launch_jseeker.py --debug
    python launch_jseeker.py --check-only
    python launch_jseeker.py --port 8510
    python launch_jseeker.py --no-kill
    python launch_jseeker.py --skip-warden
"""

import sys
from pathlib import Path

# Make gaia_launch_lib importable from the shared GAIA directory
sys.path.insert(0, str(Path(r"X:\Projects\_GAIA")))

from gaia_launch_lib import ProjectLauncher  # noqa: E402

# Read version from package without importing jseeker itself (avoids heavy deps at launch time)
_version_file = Path(__file__).parent / "jseeker" / "__init__.py"
_version = "0.3.13"
try:
    for _line in _version_file.read_text().splitlines():
        if _line.startswith("__version__"):
            _version = _line.split('"')[1]
            break
except Exception:
    pass

_PROJECT_ROOT = Path(__file__).parent.resolve()

launcher = ProjectLauncher(
    name="jSeeker",
    project_root=_PROJECT_ROOT,
    app_path=Path("ui/app.py"),
    default_port=8502,
    venv_name=".venv",
    key_imports=["streamlit", "anthropic", "yaml", "pydantic"],
    editable_extras=[str(Path(r"X:\Projects\_GAIA\_MYCEL"))],
    version=_version,
)

if __name__ == "__main__":
    launcher.run()
