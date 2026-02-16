"""jSeeker + ARGUS Co-Launch Script.

Starts both jSeeker (Streamlit Resume Engine) and ARGUS (GAIA Ecosystem Monitor)
on separate ports. Includes port conflict detection and process verification.

NOTE: For standalone launches, use:
  - python launch_jseeker.py  (jSeeker only on port 8502)
  - python launch_argus.py    (ARGUS only on port 8501)

Usage:
    python launch_both.py
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

ARGUS_DIR = Path(r"X:\Projects\_GAIA\_ARGUS")
ARGUS_APP = ARGUS_DIR / "dashboard" / "app.py"
ARGUS_PORT = 8501

processes = []


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
        import subprocess as sp

        sp.run(
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
    """Launch both jSeeker and ARGUS Streamlit apps."""
    print("=" * 60)
    print("  GAIA Co-Launch: jSeeker + ARGUS")
    print("=" * 60)

    # Step 0: Clear stale bytecode cache
    _clear_pycache()

    # Step 1: Check port availability
    print("\n  Checking ports...")
    for port, name in [(ARGUS_PORT, "ARGUS"), (JSEEKER_PORT, "jSeeker")]:
        if not _check_port(port):
            print(f"  Port {port} ({name}) is in use. Attempting to free it...")
            if _kill_port(port):
                print(f"  Port {port} freed successfully.")
            else:
                print(f"  ERROR: Cannot free port {port}. Please close the process manually.")
                print(f'  Run: powershell -Command "Get-NetTCPConnection -LocalPort {port}"')
                return
        else:
            print(f"  Port {port} ({name}): available")

    # Step 2: Launch ARGUS first (monitoring dashboard)
    if ARGUS_APP.exists():
        print(f"\n  Starting ARGUS (GAIA Ecosystem Monitor) on port {ARGUS_PORT}...")
        argus_proc = subprocess.Popen(
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
        processes.append(("ARGUS", argus_proc, ARGUS_PORT))
    else:
        print(f"\n  WARNING: ARGUS not found at {ARGUS_APP}")

    # Small delay to let ARGUS bind its port before jSeeker starts
    time.sleep(2)

    # Step 3: Launch jSeeker (Resume Engine)
    print(f"  Starting jSeeker (Resume Engine) on port {JSEEKER_PORT}...")
    jseeker_proc = subprocess.Popen(
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
    processes.append(("jSeeker", jseeker_proc, JSEEKER_PORT))

    # Step 4: Verify both processes are running
    time.sleep(3)
    all_ok = True
    for name, proc, port in processes:
        if proc.poll() is not None:
            print(f"  ERROR: {name} exited with code {proc.returncode}")
            all_ok = False
        else:
            print(f"  {name}: running (PID {proc.pid})")

    if not all_ok:
        print("\n  Some processes failed to start. Shutting down...")
        shutdown()
        return

    # Step 5: Print dashboard URLs
    print("\n" + "=" * 60)
    print(f"  ARGUS  (GAIA Monitor):  http://localhost:{ARGUS_PORT}")
    print(f"  jSeeker (Resume Engine): http://localhost:{JSEEKER_PORT}")
    print("=" * 60)
    print("  Press Ctrl+C to stop all.")
    print("=" * 60 + "\n")

    # Wait for processes
    try:
        while True:
            for name, proc, port in processes:
                if proc.poll() is not None:
                    print(f"\n  {name} (PID {proc.pid}) exited with code {proc.returncode}")
                    shutdown()
                    return
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n  Shutting down...")
        shutdown()


def shutdown():
    """Gracefully stop all running processes."""
    for name, proc, port in processes:
        if proc.poll() is None:
            print(f"  Stopping {name} (PID {proc.pid})...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    print("  All processes stopped.")


# Handle Ctrl+C gracefully
signal.signal(signal.SIGINT, lambda s, f: None)

if __name__ == "__main__":
    launch()
