"""
jSeeker Launcher - Ensures venv, dependencies, and WARDEN validation before launch.

Usage:
    python run.py              # Full pipeline: venv + deps + warden + launch
    python run.py --skip-warden  # Skip WARDEN validation
    python run.py --check-only   # Only check venv + deps, don't launch
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
APP_ENTRY = PROJECT_ROOT / "ui" / "app.py"
PORT = 8502
MYCEL_PATH = Path(r"X:\Projects\_GAIA\_MYCEL")
WARDEN_PATH = Path(r"X:\Projects\_GAIA\_WARDEN")


def get_venv_python() -> Path:
    """Get path to venv Python executable."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def get_venv_pip() -> Path:
    """Get path to venv pip executable."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def step_venv():
    """Ensure .venv exists, create if missing."""
    print("\n[1/4] Checking virtual environment...")
    venv_python = get_venv_python()

    if venv_python.exists():
        # Verify it's functional
        result = subprocess.run(
            [str(venv_python), "--version"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"  OK: .venv exists ({result.stdout.strip()})")
            return True
        else:
            print(f"  WARN: .venv broken, recreating...")

    print(f"  Creating .venv at {VENV_DIR}...")
    result = subprocess.run(
        [sys.executable, "-m", "venv", str(VENV_DIR)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  FAIL: Could not create venv: {result.stderr}")
        return False

    print(f"  OK: .venv created")
    return True


def step_dependencies():
    """Install/verify requirements.txt in venv."""
    print("\n[2/4] Checking dependencies...")
    venv_pip = get_venv_pip()
    venv_python = get_venv_python()

    if not REQUIREMENTS.exists():
        print(f"  WARN: No requirements.txt found")
        return True

    # Install requirements
    print(f"  Installing from {REQUIREMENTS.name}...")
    result = subprocess.run(
        [str(venv_pip), "install", "-r", str(REQUIREMENTS), "--quiet"],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        print(f"  WARN: Some packages failed to install:")
        # Show only errors, not the full output
        for line in result.stderr.splitlines():
            if "ERROR" in line or "error" in line:
                print(f"    {line}")
        print(f"  Continuing anyway (some deps may be optional)...")

    # Install MYCEL (editable, local)
    if MYCEL_PATH.exists():
        print(f"  Installing MYCEL (local editable)...")
        subprocess.run(
            [str(venv_pip), "install", "-e", str(MYCEL_PATH), "--quiet"],
            capture_output=True, text=True,
        )

    # Verify key imports
    check_imports = ["streamlit", "anthropic", "yaml", "pydantic"]
    missing = []
    for module in check_imports:
        result = subprocess.run(
            [str(venv_python), "-c", f"import {module}"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            missing.append(module)

    if missing:
        print(f"  WARN: Missing imports: {', '.join(missing)}")
    else:
        print(f"  OK: All key dependencies available")

    return True


def step_warden():
    """Run WARDEN governance validation."""
    print("\n[3/4] Running WARDEN validation...")
    venv_python = get_venv_python()

    if not (WARDEN_PATH / "warden" / "cli.py").exists():
        print(f"  SKIP: WARDEN not found at {WARDEN_PATH}")
        return True

    result = subprocess.run(
        [str(venv_python), "-m", "warden.cli", "validate", "--project", str(PROJECT_ROOT)],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(WARDEN_PATH)},
    )

    print(result.stdout)

    if result.returncode == 2:
        print("  FAIL: WARDEN validation failed (advisory - continuing anyway)")
    elif result.returncode == 1:
        print("  WARN: Warnings found (continuing)")
    else:
        print("  OK: All checks passed")

    return True  # Advisory mode: never block


def step_launch():
    """Launch jSeeker Streamlit app in venv."""
    print("\n[4/4] Launching jSeeker...")
    venv_python = get_venv_python()

    if not APP_ENTRY.exists():
        print(f"  FAIL: Entry point not found: {APP_ENTRY}")
        return False

    print(f"  App: {APP_ENTRY}")
    print(f"  Port: {PORT}")
    print(f"  URL: http://localhost:{PORT}")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        proc = subprocess.run(
            [
                str(venv_python), "-m", "streamlit", "run",
                str(APP_ENTRY),
                "--server.port", str(PORT),
                "--server.headless", "true",
                "--browser.serverAddress", "localhost",
            ],
            cwd=str(PROJECT_ROOT),
        )
        return proc.returncode == 0
    except KeyboardInterrupt:
        print("\n  Stopped.")
        return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="jSeeker Launcher")
    parser.add_argument("--skip-warden", action="store_true", help="Skip WARDEN validation")
    parser.add_argument("--check-only", action="store_true", help="Only check venv + deps, don't launch")
    args = parser.parse_args()

    print("=" * 50)
    print("  jSeeker Launcher")
    print("=" * 50)

    if not step_venv():
        sys.exit(1)

    if not step_dependencies():
        sys.exit(1)

    if not args.skip_warden:
        step_warden()

    if args.check_only:
        print("\n  Check complete. Use 'python run.py' to launch.")
        sys.exit(0)

    if not step_launch():
        sys.exit(1)


if __name__ == "__main__":
    main()
