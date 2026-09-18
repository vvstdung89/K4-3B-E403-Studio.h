"""Shared config constants and dataset/decision-cache helpers for the four
Discord-pipeline entry points: bot_gateway.py, run_live.py, simulate_cron.py,
dashboard_server.py.

Import-time side-effect-free by design (no SystemExit, no discord.Client()
construction, no required env vars) -- bot_gateway.py needs live Discord
credentials to import cleanly, which is exactly why dashboard_server.py used
to duplicate these constants/functions instead of importing bot_gateway.py.
This module lets both import the same definitions safely.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ai_decide.stub import Decision
from data.loader import Message, load_messages, load_test_case

MIN_HOURS_UNANSWERED = 4.0  # CSV/testcase datasets -- must match build_demo_cache.py's cache, don't change lightly
LOOKBACK_SAFETY_MARGIN_HOURS = 2.0  # added to the live threshold when fetching recent messages for a live check
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")  # only GEMINI_API_KEY is configured in .env

DISCORD_PACK_DIR = Path(__file__).resolve().parent.parent / "data" / "discord-pack"
EVAL_TESTCASES_DIR = Path(__file__).resolve().parent.parent / "eval" / "testcases"  # golden set, spec.md §7
DEMO_CACHE_DIR = Path("output/demo_cache")  # built by build_demo_cache.py
LIVE_SEEN_IDS_PATH = Path("output/.live_seen_ids.json")


def load_seen_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def save_seen_ids(path: Path, seen_ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen_ids)), encoding="utf-8")


def load_dataset_messages(dataset: str) -> list[Message]:
    """Loads a demo dataset by its selected filename -- .json is a golden-set
    case (eval/testcases/, expected_output ignored here, it's for the
    dashboard's comparison view, not the detection/AI pipeline), .csv is the
    plain discord-pack format."""
    if dataset.endswith(".json"):
        messages, _case = load_test_case(EVAL_TESTCASES_DIR / dataset)
        return messages
    return load_messages(DISCORD_PACK_DIR / dataset)


def ai_source(decision: Decision, used_cache: bool) -> str:
    if decision.rationale.startswith("[Rule-based only] Not in demo cache"):
        return "cache-miss-fallback"
    if decision.rationale.startswith("[Rule-based only]"):
        return "rule-based-cap"
    return "cache" if used_cache else "live-ai"


def load_cached_decisions(dataset: str, candidates: list) -> list[Decision] | None:
    """Loads pre-computed decisions for `dataset` from build_demo_cache.py's
    output, matched back onto the freshly-loaded `candidates` by msg_id.
    Returns None if no cache exists for this dataset, or if any candidate is
    missing from it -- an incomplete cache cannot silently clear unreviewed
    candidates, so the caller falls back to a live AI call for the whole
    batch rather than defaulting the missing ones to NOT flagged."""
    cache_path = DEMO_CACHE_DIR / f"{Path(dataset).stem}.json"
    if not cache_path.exists():
        return None
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    cached_by_id = {d["msg_id"]: d for d in cache["decisions"]}
    decisions = []
    for c in candidates:
        cached = cached_by_id.get(c.message.msg_id)
        if cached is None:
            return None
        decisions.append(
            Decision(
                candidate=c,
                still_needs_attention=cached["still_needs_attention"],
                confidence=cached["confidence"],
                rationale=cached["rationale"],
            )
        )
    return decisions
