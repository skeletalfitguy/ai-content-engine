"""Tiny idempotency guard so the pipeline can be triggered MANY times a day
(for reliability against GitHub's flaky scheduler) but only does real work ONCE.

Each module records the UTC date it last completed successfully in run_state.json.
A later trigger on the same day sees it's already done and skips — no wasted API
quota, no repeat Apify spend. If a run fails midway, the mark is never written, so
the next trigger automatically retries. That's what makes it self-healing.
"""
import json
from datetime import datetime, timezone

STATE_FILE = "run_state.json"


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def already_ran(name):
    """True if `name` already completed successfully today (UTC)."""
    return _load().get(name) == _today()


def mark_ran(name):
    s = _load()
    s[name] = _today()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


def run_once(name, fn):
    """Run fn() only if it hasn't succeeded today; mark done on success."""
    if already_ran(name):
        print(f"✅ '{name}' already ran today ({_today()}) — skipping (idempotent).")
        return
    fn()
    mark_ran(name)
