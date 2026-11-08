import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agent
import run_logger


class RunLoggingTests(unittest.TestCase):
    def test_completed_run_is_recorded_with_output_and_measurements(self):
        session = {
            "error": None,
            "selected_item": {
                "id": "lst_002",
                "title": "Y2K Baby Tee",
                "price": 18.0,
                "platform": "depop",
            },
            "outfit_suggestion": "Wear with jeans.",
            "fit_card": "A great tee for $18 on Depop.",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "runs.jsonl"
            with (
                patch.object(run_logger, "RUN_LOG", log_path),
                patch.object(agent, "_run_agent", return_value=session),
                patch.object(agent.generate, "call_count", return_value=3),
                patch.object(
                    agent.generate,
                    "token_counts",
                    side_effect=[
                        {"prompt": 10, "output": 5, "total": 15},
                        {"prompt": 30, "output": 12, "total": 42},
                    ],
                ),
            ):
                result = agent.run_agent("graphic tee", {"items": []})

            record = json.loads(log_path.read_text(encoding="utf-8"))

        self.assertIs(result, session)
        self.assertTrue(record["timestamp"].endswith("+00:00"))
        self.assertEqual(record["input"]["query"], "graphic tee")
        self.assertEqual(record["output"]["status"], "completed")
        self.assertEqual(record["output"]["selected_item"]["id"], "lst_002")
        self.assertEqual(
            record["output"]["outfit_suggestion_preview"], "Wear with jeans."
        )
        self.assertEqual(record["output"]["fit_card"], "A great tee for $18 on Depop.")
        self.assertEqual(record["model_usage"]["prompt_tokens"], 20)
        self.assertEqual(record["model_usage"]["output_tokens"], 7)
        self.assertGreaterEqual(record["duration_ms"], 0)
        self.assertIsNone(record["exception"])

    def test_raised_run_is_recorded_before_exception_is_reraised(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "runs.jsonl"
            with (
                patch.object(run_logger, "RUN_LOG", log_path),
                patch.object(agent, "_run_agent", side_effect=RuntimeError("MCP down")),
            ):
                with self.assertRaisesRegex(RuntimeError, "MCP down"):
                    agent.run_agent("graphic tee", {"items": []})

            record = json.loads(log_path.read_text(encoding="utf-8"))

        self.assertIsNone(record["output"])
        self.assertEqual(record["exception"]["type"], "RuntimeError")
        self.assertEqual(record["exception"]["message"], "MCP down")

    def test_handled_agent_error_is_recorded_in_output(self):
        session = {
            "error": "No listings matched. Try a broader description.",
            "selected_item": None,
            "outfit_suggestion": None,
            "fit_card": None,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "runs.jsonl"
            with (
                patch.object(run_logger, "RUN_LOG", log_path),
                patch.object(agent, "_run_agent", return_value=session),
            ):
                agent.run_agent("impossible query", {"items": []})

            record = json.loads(log_path.read_text(encoding="utf-8"))

        self.assertEqual(record["output"]["status"], "error")
        self.assertEqual(record["output"]["error"], session["error"])
        self.assertIsNone(record["exception"])


if __name__ == "__main__":
    unittest.main()
