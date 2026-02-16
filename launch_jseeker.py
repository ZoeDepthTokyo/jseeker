"""jSeeker Launch Script (Standalone).

Starts jSeeker (Streamlit Resume Engine) on port 8502.
Includes port conflict detection and process verification.

Usage:
    python launch_jseeker.py
"""

import socket
import subprocess
import sys
import signal
import time
from pathlib import Path

JSEEKER_DIR = Path(__file__).parent
JSEEKER_APP = JSEEKER_DIR / "ui" / "app.py"
JSEEKER_PORT = 8502

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


def _clear_pycache():
    """Clear stale __pycache__ directories to prevent import errors."""
    count = 0
    for cache_dir in JSEEKER_DIR.rglob("__pycache__"):
        if cache_dir.is_dir():
            import shutil

            shutil.rmtree(cache_dir, ignore_errors=True)
            count += 1
    if count:
        print(f"  Cleared {count} __pycache__ directories")


def launch():
    """Launch jSeeker Streamlit app."""
    global process

    print("=" * 60)
    print("  jSeeker - The Shape-Shifting Resume Engine")
    print("=" * 60)

    # Step 0: Clear stale bytecode cache
    _clear_pycache()

    # Step 1: Check port availability
    print(f"\n  Checking port {JSEEKER_PORT}...")
    if not _check_port(JSEEKER_PORT):
        print(f"  Port {JSEEKER_PORT} is in use. Attempting to free it...")
        if _kill_port(JSEEKER_PORT):
            print(f"  Port {JSEEKER_PORT} freed successfully.")
        else:
            print(f"  ERROR: Cannot free port {JSEEKER_PORT}. Please close the process manually.")
            print(f'  Run: powershell -Command "Get-NetTCPConnection -LocalPort {JSEEKER_PORT}"')
            return
    else:
        print(f"  Port {JSEEKER_PORT}: available")

    # Step 2: Launch jSeeker
    print(f"\n  Starting jSeeker on port {JSEEKER_PORT}...")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(JSEEKER_APP),
            "--server.port",
            str(JSEEKER_PORT),
            "--server.headless",
            "true",
            "--browser.serverAddress",
            "localhost",
        ],
        cwd=str(JSEEKER_DIR),
    )

    # Step 3: Verify process is running
    time.sleep(3)
    if process.poll() is not None:
        print(f"  ERROR: jSeeker exited with code {process.returncode}")
        print("\n  Check the logs above for errors.")
        return

    print(f"  jSeeker: running (PID {process.pid})")

    # Step 4: Print dashboard URL
    print("\n" + "=" * 60)
    print(f"  jSeeker Dashboard: http://localhost:{JSEEKER_PORT}")
    print("=" * 60)
    print("  Press Ctrl+C to stop.")
    print("=" * 60 + "\n")

    # Wait for process
    try:
        while True:
            if process.poll() is not None:
                print(f"\n  jSeeker (PID {process.pid}) exited with code {process.returncode}")
                return
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n  Shutting down jSeeker...")
        shutdown()


def shutdown():
    """Gracefully stop the running process."""
    global process
    if process and process.poll() is None:
        print(f"  Stopping jSeeker (PID {process.pid})...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    print("  jSeeker stopped.")


# Handle Ctrl+C gracefully
signal.signal(signal.SIGINT, lambda s, f: None)

if __name__ == "__main__":
    launch()
