"""Standalone batch runner for auto-apply.

Run this as a separate process from Streamlit to avoid asyncio event loop
conflicts on Windows (SelectorEventLoop does not support subprocess creation).
Playwright owns the event loop cleanly in this process.

Usage:
    python scripts/run_auto_apply_batch.py [--dry-run] [--headless] [--limit N] [--market CODE]

Progress is printed as JSON lines to stdout so the parent process can parse it.
All queue status updates go directly to the SQLite DB.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Force ProactorEventLoop on Windows BEFORE importing Playwright.
# Python 3.14 regressed: SelectorEventLoop may be picked up instead of
# ProactorEventLoop, and SelectorEventLoop cannot launch subprocesses.
# Playwright needs asyncio.create_subprocess_exec which requires ProactorEventLoop.
# set_event_loop_policy is deprecated in 3.14; set the loop directly instead.
if sys.platform == "win32":
    _loop = asyncio.ProactorEventLoop()
    asyncio.set_event_loop(_loop)

# Ensure jSeeker root is on the path when invoked directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright

from config import settings
from jseeker.answer_bank import load_answer_bank
from jseeker.ats_runners.greenhouse import GreenhouseRunner
from jseeker.ats_runners.workday import WorkdayRunner
from jseeker.auto_apply import AutoApplyEngine
from jseeker.tracker import get_queued_applications, init_db, update_queue_status


_LOG_FILE = Path(__file__).parent.parent / "data" / "apply_logs" / "batch_run.jsonl"


def _emit(obj: dict) -> None:
    """Print a JSON progress line AND append it to the log file."""
    line = json.dumps(obj)
    print(line, flush=True)
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-apply batch runner")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--no-headless", action="store_true", default=False)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--market", default="us")
    args = parser.parse_args()

    dry_run: bool = args.dry_run
    headless: bool = not args.no_headless

    init_db(settings.db_path)
    queued_items = get_queued_applications(limit=args.limit)

    if not queued_items:
        _emit({"type": "no_items"})
        return 0

    total = len(queued_items)
    _emit({"type": "start", "total": total, "dry_run": dry_run, "headless": headless})

    try:
        engine = AutoApplyEngine(answer_bank=load_answer_bank())
        engine.register_runner(WorkdayRunner())
        engine.register_runner(GreenhouseRunner())
    except Exception as e:
        _emit({"type": "error", "phase": "init", "error": str(e)})
        return 1

    completed = 0

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context()

            for i, item in enumerate(queued_items):
                _emit(
                    {
                        "type": "progress",
                        "index": i,
                        "total": total,
                        "id": item["id"],
                        "url": item["job_url"],
                        "platform": item["ats_platform"],
                    }
                )

                update_queue_status(item["id"], "in_progress")

                page = context.new_page()
                try:
                    result = engine.apply_with_page(
                        page=page,
                        job_url=item["job_url"],
                        resume_path=Path(item["resume_path"]),
                        market=item.get("market") or args.market,
                        dry_run=dry_run,
                    )
                    update_queue_status(
                        item["id"],
                        result.status.value,
                        cost_usd=result.cost_usd,
                    )
                    _emit(
                        {
                            "type": "item_done",
                            "id": item["id"],
                            "status": result.status.value,
                            "cost_usd": result.cost_usd,
                        }
                    )
                    completed += 1
                except Exception as e:
                    update_queue_status(item["id"], "failed_permanent")
                    _emit(
                        {
                            "type": "item_error",
                            "id": item["id"],
                            "error": str(e),
                        }
                    )
                    completed += 1
                finally:
                    page.close()

            context.close()
            browser.close()

    except Exception as e:
        _emit({"type": "fatal_error", "error": str(e)})
        return 1

    _emit({"type": "complete", "total": total, "completed": completed})
    return 0


if __name__ == "__main__":
    sys.exit(main())
