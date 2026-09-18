"""Offline checks for the batch classifier's merged Discord/dashboard callers."""

import importlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codebase"))

from ai_decide.types import Decision
from data.loader import Message
from detect.rules import explain_detection


def batch():
    now = datetime(2026, 9, 18, 15)
    messages = [
        Message(
            msg_id=f"q{i}", guild="1", channel="2", author=f"student{i}",
            is_bot=False, msg_type="message", created_at=datetime(2026, 9, 18, 9),
            reply_to=None, mentions_bot=False, n_attachments=0,
            n_chars=5, content="Help?",
        )
        for i in range(7)
    ]
    candidates = explain_detection(messages, now).candidates
    decisions = [Decision(c, i == 6, 0.9, "Reviewed") for i, c in enumerate(candidates)]
    return now, messages, candidates, decisions


class DiscordMergeTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_batch_logs_all_results_and_sends_only_unresolved(self):
        with patch.dict(os.environ, {
            "DISCORD_BOT_TOKEN": "offline-test-token",
            "DISCORD_GUILD_ID": "1", "DISCORD_CHANNEL_IDS": "2",
        }), patch("dotenv.load_dotenv"):
            gateway = importlib.import_module("bot_gateway")
        now, messages, candidates, decisions = batch()
        interaction = SimpleNamespace(followup=SimpleNamespace(send=AsyncMock()))
        with patch.object(gateway, "decide", return_value=decisions) as decide, \
             patch.object(gateway, "log_run") as log, \
             patch.object(gateway, "format_candidate_embed", side_effect=lambda d, *args, **kwargs: {"title": d.candidate.message.msg_id}):
            await gateway._reply_with_candidates(interaction, messages, now, ephemeral=True)
        decide.assert_called_once_with(candidates, all_messages=messages)
        self.assertEqual(len(log.call_args.args[0]["ai_review"]), 7)
        self.assertEqual(log.call_args.args[0]["posted"], ["q6"])
        # source="live" (the default) now sends one message per still-open
        # candidate -- each with its own embed + action-button view, instead
        # of one message batching all embeds together -- so a button can
        # attach to that one candidate specifically.
        interaction.followup.send.assert_awaited_once()
        sent = interaction.followup.send.call_args.kwargs
        self.assertEqual(sent["embed"].title, "q6")
        self.assertIn("view", sent)
        self.assertTrue(sent["ephemeral"])


class DashboardMergeTests(unittest.TestCase):
    def test_uncached_run_reviews_more_than_five_candidates_with_full_context(self):
        dashboard = importlib.import_module("dashboard_server")
        _, messages, candidates, decisions = batch()
        # The dashboard uses the last dataset timestamp as its reference clock.
        candidates = explain_detection(messages, max(m.created_at for m in messages)).candidates
        decisions = [Decision(c, i == 6, 0.9, "Reviewed") for i, c in enumerate(candidates)]
        with patch.object(dashboard, "_load_dataset_messages", return_value=messages), \
             patch.object(dashboard, "_load_cached_decisions", return_value=None), \
             patch.object(dashboard, "decide", return_value=decisions) as decide, \
             patch.object(dashboard, "log_run") as log:
            result = dashboard.run_pipeline_and_log("offline.json")
        decide.assert_called_once_with(candidates, all_messages=messages, provider=dashboard.LLM_PROVIDER)
        self.assertEqual(len(result["ai_review"]), 7)
        self.assertTrue(all(item["source"] == "live-ai" for item in result["ai_review"]))
        self.assertEqual(result["posted"], ["q6"])
        log.assert_called_once_with(result)

    def test_incomplete_cache_requires_fresh_review(self):
        dashboard = importlib.import_module("dashboard_server")
        _, _, candidates, _ = batch()
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            (cache_dir / "offline.json").write_text(json.dumps({"decisions": [
                {"msg_id": "q0", "still_needs_attention": False, "confidence": 0.9, "rationale": "Reviewed"},
            ]}), encoding="utf-8")
            with patch.object(dashboard, "DEMO_CACHE_DIR", cache_dir):
                self.assertIsNone(dashboard._load_cached_decisions("offline.json", candidates))


if __name__ == "__main__":
    unittest.main()
