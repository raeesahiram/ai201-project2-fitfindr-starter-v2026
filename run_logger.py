"""Append one structured record for each agent run."""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import config

RUN_LOG = config.RESULTS_DIR / "agent_runs.jsonl"
_write_lock = threading.Lock()


def append_run_record(record: dict) -> None:
    """Append a JSON object as one durable, newline-delimited record."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        **record,
    }
    line = json.dumps(entry, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock, RUN_LOG.open("a", encoding="utf-8") as log_file:
        log_file.write(line + "\n")
        log_file.flush()


def summarize_session(session: dict | None) -> dict | None:
    """Keep useful output while excluding private wardrobe contents."""
    if session is None:
        return None

    item = session.get("selected_item") or {}
    return {
        "status": "error" if session.get("error") else "completed",
        "error": session.get("error"),
        "selected_item": {
            key: item.get(key) for key in ("id", "title", "price", "platform")
        } if item else None,
        "outfit_suggestion": session.get("outfit_suggestion"),
        "fit_card": session.get("fit_card"),
    }
