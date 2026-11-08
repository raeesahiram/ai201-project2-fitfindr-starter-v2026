"""Run the five Shape B criteria three times and save measured evidence."""

import asyncio
import contextlib
import io
import json
import tempfile
import time
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent
import config
import generate
import mcp_client
import run_logger
import trace
from generate import ModelUnavailable
from mcp_client import MCPError
from utils.data_loader import get_example_wardrobe, load_listings

REPORT = ROOT / "results" / "criteria_eval.md"
WARDROBE = get_example_wardrobe()
MATCHING_QUERY = "vintage graphic tee under $30"
IMPOSSIBLE_QUERY = "qzxv blorptastic nebuloid quuxorium"
MATCHING_ITEM = load_listings()[1]


def _session(error=None):
    return {
        "error": error,
        "selected_item": MATCHING_ITEM if error is None else None,
        "outfit_suggestion": "Wear with jeans." if error is None else None,
        "fit_card": "A great graphic tee for $18 on Depop." if error is None else None,
    }


class Round:
    def __init__(self, number):
        self.number = number
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.log_path = Path(self._temporary_directory.name) / "runs.jsonl"
        self._logger_patch = patch.object(run_logger, "RUN_LOG", self.log_path)
        self._logger_patch.start()
        self.samples = {}

    def close(self):
        self._logger_patch.stop()
        self._temporary_directory.cleanup()

    def records(self):
        if not self.log_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
        ]

    def invoke(self, query, save_as=None, capture_output=True):
        trace.start_trace()
        stdout, stderr = io.StringIO(), io.StringIO()
        session = None
        exception = None
        stdout_context = contextlib.redirect_stdout(stdout) if capture_output else nullcontext()
        stderr_context = contextlib.redirect_stderr(stderr) if capture_output else nullcontext()
        with stdout_context, stderr_context:
            try:
                session = agent.run_agent(query, WARDROBE)
            except Exception as exc:
                exception = exc
        record = self.records()[-1]
        if save_as:
            self.samples[save_as] = {
                "record": record,
                "response": session,
                "exception": (
                    {"type": type(exception).__name__, "message": str(exception)}
                    if exception
                    else None
                ),
                "trace": stdout.getvalue().strip(),
            }
        return session, exception, record


def _criterion_one(run):
    outcomes = [
        _session() if index < 4
        else _session("Handled test failure") if index < 7
        else RuntimeError(f"Raised test failure {index}")
        for index in range(10)
    ]
    with patch.object(agent, "_run_agent", side_effect=outcomes):
        for index in range(10):
            run.invoke(
                f"criterion one run {index + 1}",
                save_as={
                    0: "c1_completed",
                    4: "c1_handled",
                    7: "c1_raised",
                }.get(index),
            )

    records = run.records()
    required = {
        "timestamp", "input", "output", "exception", "duration_ms", "model_usage"
    }
    valid = len(records) == 10
    valid &= all(required.issubset(record) for record in records)
    valid &= all(
        datetime.fromisoformat(r["timestamp"]).utcoffset() is not None
        for r in records
    )
    valid &= all(r["duration_ms"] >= 0 for r in records)
    valid &= all(
        {"calls", "prompt_tokens", "output_tokens"}.issubset(r["model_usage"])
        for r in records
    )
    valid &= sum(r["output"] is not None for r in records) == 7
    valid &= sum(r["exception"] is not None for r in records) == 3
    return (10 if valid else 0), 10


def _criterion_two(run):
    async def stalled_call(name, arguments):
        await asyncio.sleep(10)

    within_deadline = 0
    timeout = config.MCP_CALL_TIMEOUT_SECONDS
    with (
        patch.object(config, "MCP_CALL_TIMEOUT_SECONDS", 0.02),
        patch.object(mcp_client, "_call", stalled_call),
        patch.object(agent, "suggest_outfit") as suggest_outfit,
        patch.object(agent, "create_fit_card") as create_fit_card,
    ):
        timeout = config.MCP_CALL_TIMEOUT_SECONDS
        for index in range(5):
            started = time.perf_counter()
            session, exception, record = run.invoke(
                f"stalled search {index + 1}",
                save_as="c2_timeout" if index == 0 else None,
            )
            elapsed = time.perf_counter() - started
            if (
                exception is None
                and session
                and session.get("error")
                and elapsed <= timeout + 1
                and record["output"]["status"] == "error"
            ):
                within_deadline += 1
        suggest_outfit.assert_not_called()
        create_fit_card.assert_not_called()
    return within_deadline, 5


def _criterion_three(run):
    success_count = 0
    malformed = [{"id": "incomplete"}]
    with (
        patch.object(agent, "suggest_outfit") as suggest_outfit,
        patch.object(agent, "create_fit_card") as create_fit_card,
    ):
        for category in ("transport", "malformed"):
            for index in range(5):
                if category == "transport":
                    with patch.object(
                        agent,
                        "call_tool",
                        side_effect=MCPError("simulated MCP disconnect"),
                    ):
                        session, exception, record = run.invoke(
                            "graphic tee",
                            save_as="c3_transport" if index == 0 else None,
                        )
                else:
                    with patch.object(agent, "call_tool", return_value=malformed):
                        session, exception, record = run.invoke(
                            "graphic tee",
                            save_as="c3_malformed" if index == 0 else None,
                        )
                if (
                    exception is None
                    and session
                    and session.get("error")
                    and record["output"]["status"] == "error"
                ):
                    success_count += 1
        suggest_outfit.assert_not_called()
        create_fit_card.assert_not_called()
    return success_count, 10


class _BlankResponse:
    text = "   "


class _BlankModels:
    @staticmethod
    def generate_content(**kwargs):
        return _BlankResponse()


class _RateLimitedModels:
    @staticmethod
    def generate_content(**kwargs):
        raise RuntimeError("429 rate limit")


class _Client:
    def __init__(self, models):
        self.models = models


def _criterion_four(run):
    handled = 0
    for mode, models in (
        ("blank", _BlankModels()),
        ("rate_limit", _RateLimitedModels()),
    ):
        for index in range(5):
            trace.start_trace()
            stdout, stderr = io.StringIO(), io.StringIO()
            with (
                patch.object(agent, "call_tool", return_value=[MATCHING_ITEM]),
                patch.object(generate, "_get_client", return_value=_Client(models)),
                patch.object(generate, "_wait_for_slot"),
                patch.object(generate.time, "sleep"),
                patch.object(generate, "_session_calls", 0),
                patch.object(config, "CACHE_ENABLED", False),
                patch.object(config, "MAX_RETRIES", 2),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                session, exception, record = run.invoke(
                    MATCHING_QUERY,
                    save_as=(
                        f"c4_{mode}" if index == 0 else None
                    ),
                )
            if (
                exception is None
                and session
                and session.get("error")
                and session.get("fit_card") is None
                and record["output"]["status"] == "error"
            ):
                handled += 1
    return handled, 10


def _criterion_five(run):
    completed = 0
    with (
        patch.object(
            agent, "suggest_outfit", return_value="Wear with jeans."
        ) as outfit,
        patch.object(
            agent,
            "create_fit_card",
            return_value="A great graphic tee for $18 on Depop.",
        ) as card,
        patch.object(trace, "step"),
    ):
        for index in range(5):
            session, exception, record = run.invoke(
                MATCHING_QUERY,
                save_as="c5_matching" if index == 0 else None,
                capture_output=False,
            )
            if (
                exception is None
                and session
                and not session.get("error")
                and session.get("fit_card")
                and record["output"]["status"] == "completed"
            ):
                completed += 1
        assert outfit.call_count == 5
        assert card.call_count == 5
    return completed, 5


def _render_sample(label, sample):
    lines = [f"**{label}** (`agent.py::run_agent`, `run_logger.append_run_record`)"]
    if sample["response"] is not None:
        response = sample["response"]
        selected_item = response.get("selected_item") or {}
        lines += [
            "",
            "Observed session response fields:",
            "```json",
            json.dumps(
                {
                    "error": response.get("error"),
                    "selected_item_id": selected_item.get("id"),
                    "outfit_suggestion_present": bool(response.get("outfit_suggestion")),
                    "fit_card_present": bool(response.get("fit_card")),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "```",
        ]
    if sample["exception"] is not None:
        lines += [
            "",
            "Raised exception:",
            "```json",
            json.dumps(sample["exception"], sort_keys=True),
            "```",
        ]
    lines += ["", "Actual structured log record:", "```json",
              json.dumps(sample["record"], ensure_ascii=False, sort_keys=True),
              "```"]
    return "\n".join(lines)


def main():
    criteria = [
        ("1. Every run leaves a structured record", "10/10"),
        ("2. A stalled MCP search stops within its deadline", "5/5"),
        ("3. MCP transport and malformed results stop safely", "10/10"),
        ("4. Model failures are returned and logged", "10/10"),
        ("5. The existing matching flow still completes", "5/5"),
    ]
    runners = [
        _criterion_one, _criterion_two, _criterion_three,
        _criterion_four, _criterion_five,
    ]
    results = {name: [] for name, _ in criteria}
    samples = {}

    for round_number in range(1, 4):
        run = Round(round_number)
        try:
            for (name, _), runner in zip(criteria, runners):
                passed, total = runner(run)
                results[name].append((passed, total))
            samples.update(run.samples)
        finally:
            run.close()

    lines = [
        "# Shape B criteria evaluation",
        "",
        "Generated by `tests/evaluate_shape_b.py`; each column is a separate "
        "full evaluation round. Failure cases are simulated; matching-path "
        "trials use deterministic model-helper responses and the actual MCP "
        "search path, without an external provider call.",
        "",
        "| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name, target in criteria:
        values = results[name]
        formatted = [f"{passed}/{total}" for passed, total in values]
        all_met = all(passed == total for passed, total in values)
        lines.append(
            f"| {name} | {target} | {formatted[0]} | {formatted[1]} | "
            f"{formatted[2]} | {'MET' if all_met else 'MISSED'} |"
        )

    lines += ["", "## Actual output from Run 1", ""]
    for key, label in [
        ("c1_completed", "Criterion 1 — completed record"),
        ("c1_handled", "Criterion 1 — handled error record"),
        ("c1_raised", "Criterion 1 — raised exception record"),
        ("c2_timeout", "Criterion 2 — stalled MCP timeout"),
        ("c3_transport", "Criterion 3 — MCP transport failure"),
        ("c3_malformed", "Criterion 3 — malformed search response"),
        ("c4_blank", "Criterion 4 — blank model response"),
        ("c4_rate_limit", "Criterion 4 — exhausted rate limit"),
        ("c5_matching", "Criterion 5 — matching flow with stubbed model output"),
    ]:
        lines += [f"### {label}", "", _render_sample(label, samples[key]), ""]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
