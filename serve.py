#!/usr/bin/env python3
"""
FitFindr over HTTP. ← UNIT 9

    python serve.py                       run it on your machine
    gunicorn serve:app                    run it the way a host runs it

Everything else in this repo exits after one command. A host has nothing to
keep running, so a command line cannot be deployed. This file is the smallest
thing that can: it starts a web server, waits, and hands each request to the
same `run_agent()` your CLI calls. **No new agent logic lives here.** If your
loop works from `python app.py ask`, it works from here; if it doesn't, fix it
there, not in this file.

Two routes:

    POST /ask       {"query": "vintage graphic tee under $30",
                     "wardrobe": {...}}     ← wardrobe is optional
    GET  /health    is it awake?
    GET  /metrics   request and model-use totals for this process

`/ask` returns the session dict from `run_agent()` as JSON, unchanged — the
same keys you print from the command line, including `error`. Read
`session["error"]` first, exactly as you do everywhere else.

It runs **one request at a time**, and one route is deliberately slower than a
web server has to be. The reason is worth reading before you deploy: see the
note above `_one_at_a_time` below — it also decides which gunicorn worker you
can use.

Each /ask request emits a JSON log line with a request ID, status, outcome,
duration, queue wait, model calls, and tokens. GET /metrics exposes
process-local totals, which reset when the process restarts.
"""

import json
import os
import sys
import threading
import time
import uuid

# config first, and before anything that talks to the model: it loads your .env
# and fixes the Windows console encoding for every module that imports it.
import config  # noqa: F401

from flask import Flask, jsonify, request

from agent import run_agent
import generate
import trace
from utils.data_loader import get_example_wardrobe

app = Flask(__name__)


# ── one request at a time ─────────────────────────────────────────────────────
# Here's why this exists.
#
# A web server will happily run two requests at once. Two things in this repo
# assume otherwise:
#
#   • If you moved a tool onto MCP in unit 4, `mcp_client.call_tool` starts
#     `mcp_server.py` as a separate process over stdio, one per call. Two
#     overlapping requests means two extra Python interpreters, and the free
#     tier you're deploying to has 512 MB for all of it. That is the reason
#     that would still be here even if everything else were perfect.
#   • `generate.py`'s pacing window and its call counter are plain module
#     globals — deliberately, because that file is teaching pacing and quota,
#     not locking. Two threads sharing them means the per-minute limiter is
#     counting something that isn't true.
#
# What the lock covers is exactly the agent run: the part that spawns
# processes and calls the model. Reading the request, rejecting a bad one, and
# turning the answer into JSON all happen outside it — so a request with a
# malformed body comes straight back with a 400 instead of queueing behind
# somebody else's agent.
#
# Serialising the runs costs you nothing here — this is one user asking one
# question — and it keeps the deployed behaviour identical to the CLI's. When
# that stops being an acceptable trade, the fix is a real queue, not a bigger
# lock.
#
# The same constraint decides your start command, and this is the part that
# bites in deployment rather than on your machine. `mcp_client.call_tool`
# wraps `asyncio.run()`, and `asyncio.run()` refuses to start when an event
# loop is already running. An async worker always has one running. So under
# `gunicorn -k gevent` (or `-k eventlet`, or `serve:app` wrapped for an ASGI
# server like uvicorn) EVERY MCP call fails with "asyncio.run() cannot be
# called from a running event loop" — not some of them under load, all of
# them, every time, in a place your laptop never showed you.
#
#     gunicorn serve:app              ← right: the DEFAULT sync worker
#     gunicorn -k gevent serve:app    ← breaks every MCP call you make

_one_at_a_time = threading.Lock()
_metrics_lock = threading.Lock()
_metrics = {
    "requests": 0,
    "failures": 0,
    "duration_ms_total": 0.0,
    "model_calls": 0,
    "tokens": 0,
}


def _record_request(
    request_id: str,
    started_at: float,
    status: int,
    outcome: str,
    model_calls: int = 0,
    tokens: int = 0,
    lock_wait_ms: float = 0.0,
) -> None:
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    with _metrics_lock:
        _metrics["requests"] += 1
        _metrics["failures"] += int(outcome != "success")
        _metrics["duration_ms_total"] += duration_ms
        _metrics["model_calls"] += model_calls
        _metrics["tokens"] += tokens

    print(
        json.dumps(
            {
                "event": "ask_request",
                "request_id": request_id,
                "status": status,
                "outcome": outcome,
                "duration_ms": duration_ms,
                "lock_wait_ms": round(lock_wait_ms, 2),
                "model_calls": model_calls,
                "tokens": tokens,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=sys.stdout,
        flush=True,
    )


@app.get("/health")
def health():
    """Is the server awake? A host pings something like this to find out."""
    return jsonify({"status": "ok"})


@app.get("/metrics")
def metrics():
    """Return process-local request and model usage counters."""
    with _metrics_lock:
        snapshot = dict(_metrics)
    snapshot["duration_ms_avg"] = (
        round(snapshot["duration_ms_total"] / snapshot["requests"], 2)
        if snapshot["requests"]
        else 0.0
    )
    return jsonify(snapshot)


@app.post("/ask")
def ask():
    """
    Run the agent on one query.

    In:   {"query": "...", "wardrobe": {...}}   wardrobe optional — leave it
                                                out and you get the same
                                                example wardrobe the CLI uses.
    Out:  the session dict from run_agent(), as JSON.
    """
    started_at = time.perf_counter()
    request_id = uuid.uuid4().hex[:12]
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        _record_request(request_id, started_at, 400, "invalid_request")
        response = jsonify({"error": "Send a JSON object with a 'query' field."})
        response.headers["X-Request-ID"] = request_id
        return response, 400

    query_value = payload.get("query")
    query = query_value.strip() if isinstance(query_value, str) else ""
    if not query:
        _record_request(request_id, started_at, 400, "invalid_request")
        response = jsonify({
            "error": "Send JSON with a non-empty 'query' string, e.g. "
                     '{"query": "vintage graphic tee under $30"}'
        })
        response.headers["X-Request-ID"] = request_id
        return response, 400

    wardrobe = payload.get("wardrobe")
    if not isinstance(wardrobe, dict):
        wardrobe = get_example_wardrobe()

    # A queued request should look like a queued request. Without this the
    # second caller just sits there, and "slow" and "waiting its turn" are
    # indistinguishable from the outside — which is how people conclude the
    # deployment is broken when it is behaving exactly as designed.
    #
    # This is NOT the logging you add in the follow-along. It prints nothing
    # on the normal path, carries no timing and counts nothing; it says only
    # that this request had to wait. `locked()` can be a moment out of date,
    # so the note is occasionally missed — which costs nothing, because
    # nothing depends on it.
    if _one_at_a_time.locked():
        print(
            "  [serve] another request is still running. This one is waiting "
            "its turn — serve.py handles one at a time, on purpose.",
            file=sys.stderr,
            flush=True,
        )

    failure = None
    session = None
    lock_started = time.perf_counter()
    lock_wait_ms = 0.0
    model_calls = 0
    tokens = 0
    with _one_at_a_time:
        lock_wait_ms = (time.perf_counter() - lock_started) * 1000
        calls_before = generate.call_count()
        tokens_before = generate.token_counts()["total"]
        trace_output_enabled = trace.set_console_output(False)
        try:
            session = run_agent(query, wardrobe)
        except Exception as exc:  # noqa: BLE001 — a 500 with a sentence beats a hang
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            model_calls = generate.call_count() - calls_before
            tokens = generate.token_counts()["total"] - tokens_before
            trace.set_console_output(trace_output_enabled)
            trace.start_trace()

    # Outside the lock: building a response is not work the next caller should
    # be waiting on.
    if failure is not None:
        _record_request(
            request_id, started_at, 500, "exception",
            model_calls, tokens, lock_wait_ms
        )
        response = jsonify({"error": failure})
        response.headers["X-Request-ID"] = request_id
        return response, 500

    if not isinstance(session, dict):
        _record_request(
            request_id, started_at, 500, "invalid_agent_response",
            model_calls, tokens, lock_wait_ms
        )
        response = jsonify({"error": "The agent returned an unexpected response."})
        response.headers["X-Request-ID"] = request_id
        return response, 500

    outcome = "agent_error" if session.get("error") else "success"
    _record_request(
        request_id, started_at, 200, outcome, model_calls, tokens, lock_wait_ms
    )
    response = jsonify(session)
    response.headers["X-Request-ID"] = request_id
    return response


if __name__ == "__main__":
    # PORT and 0.0.0.0 are not decoration. A host tells you which port to
    # listen on through PORT, and it reaches your process from outside the
    # container — bind 127.0.0.1 and nothing but the container itself can
    # connect, which looks exactly like a broken app from the browser.
    port = int(os.getenv("PORT", "5000"))

    # Never on by default. Flask's debugger executes code typed into a browser,
    # and a deployed app with it on is a stranger's shell. Set AI201_DEBUG=1 in
    # your own terminal when you want the reloader.
    debug = os.getenv("AI201_DEBUG", "0") == "1"

    print(f"\nFitFindr is listening on http://localhost:{port}")
    print("It runs one request at a time — a second one waits for the first.")
    print("Ask it something (single quotes, as always):\n")
    print(
        f"  curl -X POST http://localhost:{port}/ask \\\n"
        f"    -H 'Content-Type: application/json' \\\n"
        f"    -d '{{\"query\": \"vintage graphic tee under $30\"}}'\n"
    )
    print("Ctrl-C to stop.\n")

    app.run(host="0.0.0.0", port=port, debug=debug)
