"""ARGUS Launch Script (Standalone).

Starts ARGUS (GAIA Ecosystem Monitor) on port 8501.
Includes port conflict detection and process verification.

Usage:
    python launch_argus.py
"""

import socket
import subprocess
import sys
import signal
import time
from pathlib import Path

ARGUS_DIR = Path(r"X:\Projects\_GAIA\_ARGUS")
ARGUS_APP = ARGUS_DIR / "dashboard" / "app.py"
ARGUS_PORT = 8501

process = None


def _check_port(port: int) -> bool:
    """Check if a port is available. Returns True if free, False if in use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


def _kill_port(port: int) -> bool:
    """Attempt to kill whatever process is using a port. Returns True if freed."""
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
                f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        time.sleep(1)
        return _check_port(port)
    except Exception:
        return False


def launch():
    """Launch ARGUS Streamlit app."""
    global process

    print("=" * 60)
    print("  ARGUS - GAIA Ecosystem Monitor")
    print("=" * 60)

    # Step 1: Check if ARGUS exists
    if not ARGUS_APP.exists():
        print(f"\n  ERROR: ARGUS not found at {ARGUS_APP}")
        print("  Please ensure ARGUS is installed at X:\\Projects\\_GAIA\\_ARGUS")
        return

    # Step 2: Check port availability
    print(f"\n  Checking port {ARGUS_PORT}...")
    if not _check_port(ARGUS_PORT):
        print(f"  Port {ARGUS_PORT} is in use. Attempting to free it...")
        if _kill_port(ARGUS_PORT):
            print(f"  Port {ARGUS_PORT} freed successfully.")
        else:
            print(f"  ERROR: Cannot free port {ARGUS_PORT}. Please close the process manually.")
            print(f'  Run: powershell -Command "Get-NetTCPConnection -LocalPort {ARGUS_PORT}"')
            return
    else:
        print(f"  Port {ARGUS_PORT}: available")

    # Step 3: Launch ARGUS
    print(f"\n  Starting ARGUS on port {ARGUS_PORT}...")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ARGUS_APP),
            "--server.port",
            str(ARGUS_PORT),
            "--server.headless",
            "true",
            "--browser.serverAddress",
            "localhost",
        ],
        cwd=str(ARGUS_DIR / "dashboard"),
    )

    # Step 4: Verify process is running
    time.sleep(3)
    if process.poll() is not None:
        print(f"  ERROR: ARGUS exited with code {process.returncode}")
        print("\n  Check the logs above for errors.")
        return

    print(f"  ARGUS: running (PID {process.pid})")

    # Step 5: Print dashboard URL
    print("\n" + "=" * 60)
    print(f"  ARGUS Dashboard: http://localhost:{ARGUS_PORT}")
    print("=" * 60)
    print("  Press Ctrl+C to stop.")
    print("=" * 60 + "\n")

    # Wait for process
    try:
        while True:
            if process.poll() is not None:
                print(f"\n  ARGUS (PID {process.pid}) exited with code {process.returncode}")
                return
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n  Shutting down ARGUS...")
        shutdown()


def shutdown():
    """Gracefully stop the running process."""
    global process
    if process and process.poll() is None:
        print(f"  Stopping ARGUS (PID {process.pid})...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    print("  ARGUS stopped.")


# Handle Ctrl+C gracefully
signal.signal(signal.SIGINT, lambda s, f: None)

if __name__ == "__main__":
    launch()
