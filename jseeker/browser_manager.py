"""Persistent Playwright browser manager for fast PDF rendering.

This module maintains a single Playwright instance in a subprocess to avoid the
5-15s Chromium startup overhead on every PDF render. After the first render,
subsequent PDFs take only 1-2s (90% faster).

The browser runs in a subprocess to avoid conflicts with Streamlit's event loop.
"""

from __future__ import annotations

import atexit
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

_BROWSER_SUBPROCESS: Optional[subprocess.Popen] = None
_RENDER_COUNT = 0
_MAX_RENDERS_BEFORE_RESTART = 50  # Prevent memory leaks


def _start_browser_subprocess() -> subprocess.Popen:
    """Start a persistent Playwright browser in a subprocess."""
    script = """
import sys
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

# Playwright instance kept alive
pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True)

# Signal ready
print("READY", flush=True)

# Wait for render commands on stdin
for line in sys.stdin:
    line = line.strip()
    if not line or line == "EXIT":
        break

    parts = line.split("|", 1)
    if len(parts) != 2:
        print("ERROR:Invalid command format", flush=True)
        continue

    html_path, pdf_path = parts

    try:
        page = browser.new_page()
        page.goto(f"file:///{Path(html_path).as_posix()}")
        page.pdf(
            path=pdf_path,
            format="Letter",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        page.close()
        print("OK", flush=True)
    except Exception as e:
        print(f"ERROR:{str(e)[:200]}", flush=True)

browser.close()
pw.stop()
"""

    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    # Wait for READY signal (max 30s)
    start = time.time()
    while time.time() - start < 30:
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"Browser subprocess died: {stderr[:500]}")

        line = proc.stdout.readline().strip()
        if line == "READY":
            return proc

        time.sleep(0.1)

    proc.terminate()
    raise TimeoutError("Browser subprocess did not start within 30s")


def _get_browser_subprocess() -> subprocess.Popen:
    """Get or create the persistent browser subprocess."""
    global _BROWSER_SUBPROCESS, _RENDER_COUNT

    # Restart browser every N renders to prevent memory leaks
    if _RENDER_COUNT >= _MAX_RENDERS_BEFORE_RESTART:
        _cleanup_browser()
        _RENDER_COUNT = 0

    if _BROWSER_SUBPROCESS is None or _BROWSER_SUBPROCESS.poll() is not None:
        _BROWSER_SUBPROCESS = _start_browser_subprocess()
        atexit.register(_cleanup_browser)

    return _BROWSER_SUBPROCESS


def _cleanup_browser():
    """Terminate the persistent browser subprocess."""
    global _BROWSER_SUBPROCESS
    if _BROWSER_SUBPROCESS and _BROWSER_SUBPROCESS.poll() is None:
        try:
            _BROWSER_SUBPROCESS.stdin.write("EXIT\n")
            _BROWSER_SUBPROCESS.stdin.flush()
            _BROWSER_SUBPROCESS.wait(timeout=5)
        except Exception:
            _BROWSER_SUBPROCESS.terminate()
            try:
                _BROWSER_SUBPROCESS.wait(timeout=2)
            except subprocess.TimeoutExpired:
                _BROWSER_SUBPROCESS.kill()
        _BROWSER_SUBPROCESS = None


def html_to_pdf_fast(html: str, output_path: Path) -> Path:
    """Convert HTML to PDF using the persistent browser (fast after first call).

    First call: 5-15s (browser startup)
    Subsequent calls: 1-2s (90% faster)

    Args:
        html: HTML content to render.
        output_path: Where to save the PDF.

    Returns:
        Path to generated PDF.

    Raises:
        RuntimeError: If PDF generation fails.
    """
    global _RENDER_COUNT

    # Write HTML to temp file
    html_tmp = Path(tempfile.mktemp(suffix=".html"))
    html_tmp.write_text(html, encoding="utf-8")

    try:
        browser_proc = _get_browser_subprocess()

        # Send render command: html_path|pdf_path
        cmd = f"{html_tmp}|{output_path}\n"
        browser_proc.stdin.write(cmd)
        browser_proc.stdin.flush()

        # Wait for response
        response = browser_proc.stdout.readline().strip()

        if response == "OK":
            _RENDER_COUNT += 1
            return output_path
        elif response.startswith("ERROR:"):
            error_msg = response[6:]
            raise RuntimeError(f"PDF generation failed: {error_msg}")
        else:
            raise RuntimeError(f"Unexpected browser response: {response}")

    finally:
        html_tmp.unlink(missing_ok=True)
