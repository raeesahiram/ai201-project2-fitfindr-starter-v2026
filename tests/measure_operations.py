"""Measure local stage latency, repeated-search caching, and a 10x HTTP burst."""

import asyncio
import concurrent.futures
import json
import statistics
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
import sys
from unittest.mock import patch
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent
import config
import mcp_client
import run_logger
import serve
import trace

REPORT = ROOT / "results" / "operations_check.md"
QUERY = "vintage graphic tee under $30"
WARDROBE = {"items": []}


async def _call_uncached(name, arguments):
    return await asyncio.wait_for(
        mcp_client._call(name, arguments),
        timeout=config.MCP_CALL_TIMEOUT_SECONDS,
    )


def _record_from(log_path):
    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    return records[-1]


def _percentile(values, fraction):
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return ordered[index]


def _send_request(url, barrier=None):
    if barrier is not None:
        barrier.wait()
    started = time.perf_counter()
    request = urllib.request.Request(
        url,
        data=json.dumps({"query": QUERY}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read())
        status = response.status
    return {
        "status": status,
        "outcome": "error" if body.get("error") else "success",
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        log_path = Path(temp_dir) / "agent_runs.jsonl"
        baseline = []
        improved = []

        with (
            patch.object(run_logger, "RUN_LOG", log_path),
            patch.object(agent, "suggest_outfit", return_value="Test outfit"),
            patch.object(agent, "create_fit_card", return_value="Test fit card"),
            patch.object(trace, "step"),
        ):
            for _ in range(3):
                with patch.object(
                    agent,
                    "call_tool",
                    side_effect=lambda name, arguments: asyncio.run(
                        _call_uncached(name, arguments)
                    ),
                ):
                    started = time.perf_counter()
                    session = agent.run_agent(QUERY, WARDROBE)
                total_ms = (time.perf_counter() - started) * 1000
                if session.get("error"):
                    raise RuntimeError(session["error"])
                record = _record_from(log_path)
                baseline.append(
                    {
                        "total_ms": round(total_ms, 2),
                        "stages_ms": record["stage_durations_ms"],
                        "model_calls": record["model_usage"]["calls"],
                    }
                )

            mcp_client.clear_search_cache()
            for _ in range(3):
                started = time.perf_counter()
                session = agent.run_agent(QUERY, WARDROBE)
                total_ms = (time.perf_counter() - started) * 1000
                if session.get("error"):
                    raise RuntimeError(session["error"])
                record = _record_from(log_path)
                improved.append(
                    {
                        "total_ms": round(total_ms, 2),
                        "stages_ms": record["stage_durations_ms"],
                        "model_calls": record["model_usage"]["calls"],
                    }
                )

            server = make_server("127.0.0.1", 0, serve.app, threaded=True)
            server_thread = threading.Thread(
                target=server.serve_forever, daemon=True
            )
            server_thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                mcp_client.clear_search_cache()
                normal = _send_request(f"{base_url}/ask")

                mcp_client.clear_search_cache()
                barrier = threading.Barrier(10)
                load_started = time.perf_counter()
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
                    futures = [
                        pool.submit(_send_request, f"{base_url}/ask", barrier)
                        for _ in range(10)
                    ]
                    burst = [future.result() for future in futures]
                load_batch_ms = (time.perf_counter() - load_started) * 1000
                metrics_request = urllib.request.Request(f"{base_url}/metrics")
                with urllib.request.urlopen(metrics_request, timeout=10) as response:
                    metrics = json.loads(response.read())
            finally:
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=5)

            all_records = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]

    burst_records = all_records[7:]
    if len(burst_records) != 10:
        raise RuntimeError(
            f"Expected 10 agent records for the load burst, got {len(burst_records)}"
        )
    burst_mcp_ms = [
        record["stage_durations_ms"]["mcp_search"] for record in burst_records
    ]
    before_median = statistics.median(row["total_ms"] for row in baseline)
    after_median = statistics.median(row["total_ms"] for row in improved)
    speedup = before_median / after_median if after_median else float("inf")
    report_lines = [
        "# Local latency, cache improvement, and load check",
        "",
        "Generated by `tests/measure_operations.py`. Model-dependent helpers "
        "return deterministic test strings so this measures local control-flow "
        "and MCP overhead without a live Gemini key. The search-listings MCP "
        "server and HTTP route are real. Cache data are reset before each "
        "comparison block.",
        "",
        "## Baseline and after improvement",
        "",
        "The baseline bypasses the new result cache and performs an MCP "
        "subprocess call on each trial. The after block uses the bounded "
        "process-local cache: its first identical request is a miss; the next "
        "two are hits. Times are end-to-end `run_agent` durations; the stage "
        "columns come from the JSONL records.",
        "",
        "| Trial | Baseline total ms | Baseline MCP ms | After total ms | After MCP ms | After cache behavior |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    for index, (before, after) in enumerate(zip(baseline, improved), 1):
        behavior = "miss" if index == 1 else "hit"
        report_lines.append(
            f"| {index} | {before['total_ms']:.2f} | "
            f"{before['stages_ms']['mcp_search']:.3f} | "
            f"{after['total_ms']:.2f} | "
            f"{after['stages_ms']['mcp_search']:.3f} | {behavior} |"
        )
    report_lines += [
        "",
        f"Median total: {before_median:.2f} ms before and "
        f"{after_median:.2f} ms after; repeated-query speedup "
        f"{speedup:.1f}× in this run.",
        "",
        "## Latency breakdown",
        "",
        "Per-stage milliseconds from the baseline JSONL records:",
        "",
        "| Trial | Query parse | MCP search | Outfit helper | Fit-card helper | Total run | Other (total minus stages) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, row in enumerate(baseline, 1):
        stages = row["stages_ms"]
        other = max(
            0.0,
            row["total_ms"]
            - sum(stages.values()),
        )
        report_lines.append(
            f"| {index} | {stages['query_parse']:.3f} | "
            f"{stages['mcp_search']:.3f} | {stages['suggest_outfit']:.3f} | "
            f"{stages['create_fit_card']:.3f} | {row['total_ms']:.2f} | "
            f"{other:.3f} |"
        )
    report_lines += [
        "",
        "The model helpers are stubs in this benchmark, so their near-zero "
        "times are not estimates of Gemini latency. MCP process startup and "
        "the MCP handshake/search dominate the measured local path.",
        "",
        "## Local HTTP load observation",
        "",
        "The `serve.py` Flask app ran on an ephemeral `127.0.0.1` port. "
        "A normal-rate observation is one request with an empty search cache. "
        "The 10× burst is ten simultaneous identical requests; `serve.py` "
        "serializes agent runs, and the first search warms the local cache "
        "for the next nine. Deterministic outfit/fit-card helpers avoid live "
        "provider calls. Client and Flask request durations include time "
        "waiting for the serial request lock.",
        "",
        f"- Normal single request: **{normal['duration_ms']:.2f} ms**, "
        f"HTTP {normal['status']}, {normal['outcome']}.",
        f"- Ten-request burst duration: **{load_batch_ms:.2f} ms** "
        f"({10000 / load_batch_ms:.2f} requests/second at the batch level).",
        f"- Burst request latency: min **{min(r['duration_ms'] for r in burst):.2f} ms**, "
        f"median **{statistics.median(r['duration_ms'] for r in burst):.2f} ms**, "
        f"p90 **{_percentile([r['duration_ms'] for r in burst], .9):.2f} ms**, "
        f"max **{max(r['duration_ms'] for r in burst):.2f} ms**.",
        f"- Outcomes: {sum(r['status'] == 200 and r['outcome'] == 'success' for r in burst)}/10 "
        f"successful HTTP 200 responses. Flask process metrics: "
        f"{metrics['requests']} requests, {metrics['failures']} failures, "
        f"{metrics['duration_ms_avg']:.2f} ms average server duration.",
        "",
        "Agent-stage timings from the ten burst records show the cache "
        "effect separately from HTTP lock wait:",
        "",
        "| Request | Agent total ms | MCP search ms |",
        "|---:|---:|---:|",
    ]
    for index, record in enumerate(burst_records, 1):
        report_lines.append(
            f"| {index} | {record['duration_ms']:.2f} | "
            f"{record['stage_durations_ms']['mcp_search']:.3f} |"
        )
    report_lines += [
        "",
        f"The first MCP search took {burst_mcp_ms[0]:.3f} ms; the remaining "
        f"nine took {statistics.median(burst_mcp_ms[1:]):.3f} ms median from "
        "the warm cache. Similar client response times do not mean the cache "
        "missed: they include serial queue waiting before each fast agent run.",
        "",
        "This is a local synthetic burst against one process, not a hosted "
        "deployment or a test of concurrent live Gemini quota behavior. "
        "The CLI command is `python app.py ask 'vintage graphic tee under "
        "$30'`; start the HTTP app locally with `python serve.py`. "
        "`gunicorn serve:app` is the documented host-compatible command, "
        "but was not run as a separate server or deployed here.",
        "",
        f"The report's agent JSONL contained {len(all_records)} records across "
        "baseline, after, normal-rate, and load requests.",
    ]
    REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(REPORT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
