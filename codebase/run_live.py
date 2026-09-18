"""Real single-tick run of the flowchart's cron cycle (outputs/workflow.jpg,
steps 1-5) against a live Discord server -- the live counterpart to
simulate_cron.py's fast historical replay of the static CSV pack.

Meant to be invoked every 30 minutes by a real OS scheduler, not a sleeping
Python loop -- e.g. a crontab entry:

    */30 * * * * cd /path/to/codebase && .venv/bin/python run_live.py --send-to-discord

Run by hand from the codebase/ directory:

    python3 run_live.py                      # dry run, prints new candidates
    python3 run_live.py --send-to-discord     # also posts new candidates

Requires .env: DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, DISCORD_CHANNEL_IDS
(comma-separated) -- a real Discord Bot application, separate from the
DISCORD_WEBHOOK_URL used for outbound delivery (see .env.example).

Each run fetches a rolling lookback window (MIN_HOURS_UNANSWERED + a safety
margin, not just the 30-min tick interval -- see data/discord_live.py's
docstring for why), then reports a msg_id only the first time it crosses
the threshold: seen_ids is persisted to output/.live_seen_ids.json between
runs, since every real cron invocation is a fresh process with nothing left
in memory from the last one.

--csv <path> swaps the message source for the static data pack instead of
a real Discord fetch -- for validating this exact script (rolling window,
disk-persisted dedup, real embed posting) when bot access to the target
server isn't available yet. No DISCORD_BOT_TOKEN/GUILD_ID/CHANNEL_IDS
needed in this mode; --now optionally pins the reference clock (default:
the pack's own latest timestamp, same reasoning as main.py's --now -- real
wall-clock time would put every message trivially past the threshold):

    python3 run_live.py --csv data/discord-pack/k4_messages.csv
    python3 run_live.py --csv data/discord-pack/k4_messages.csv --send-to-discord
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from ai_decide.stub import Decision, decide
from data.discord_live import fetch_recent_messages
from data.loader import load_messages
from detect.rules import find_unanswered_questions
from notify.discord_client import send_embeds_to_discord
from notify.formatter import format_candidate_embed, format_report

load_dotenv()  # must run before any os.environ.get() below, or .env-only values are silently ignored

MIN_HOURS_UNANSWERED = 4.0  # matches detect.rules.find_unanswered_questions's default
LOOKBACK_SAFETY_MARGIN_HOURS = 2.0  # covers a slow/delayed cron run without missing a candidate
MAX_CONTEXT_HOURS = MIN_HOURS_UNANSWERED + LOOKBACK_SAFETY_MARGIN_HOURS  # bounds the LLM context window
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")  # only GEMINI_API_KEY is configured in .env
# No model_name is passed to decide() -- ai_decide/llm_factory.py already
# resolves the right one per provider (OPENAI_MODEL/GEMINI_MODEL/ANTHROPIC_MODEL,
# see .env.example). Passing one here would hardcode a Gemini-shaped model
# name that breaks if LLM_PROVIDER is ever switched to openai/anthropic.
MAX_AI_REVIEW_PER_CALL = 5  # stay well under the free tier's per-minute quota
LIVE_SEEN_IDS_PATH = Path("output/.live_seen_ids.json")
CSV_TEST_SEEN_IDS_PATH = Path("output/.live_seen_ids.csv_test.json")


def _decide_with_ai_cap(candidates: list, all_messages: list) -> list[Decision]:
    """AI-reviews at most MAX_AI_REVIEW_PER_CALL candidates (oldest-waiting
    first, matching find_unanswered_questions's own sort order) -- the rest
    stay rule-based-only, defaulting to NOT flagged. detect/rules.py now
    only excludes bot messages, so the cap-overflow set is most of every
    message, not a small handful of genuine candidates -- defaulting it to
    "needs attention" would flood Discord instead of covering a rare edge
    case."""
    ai_batch, rule_based_only = candidates[:MAX_AI_REVIEW_PER_CALL], candidates[MAX_AI_REVIEW_PER_CALL:]
    decisions = decide(ai_batch, all_messages=all_messages, provider=LLM_PROVIDER) if ai_batch else []
    decisions += [
        Decision(
            candidate=c,
            still_needs_attention=False,
            confidence=None,
            rationale="[Rule-based only] Not yet AI-reviewed -- over the per-call AI review cap",
        )
        for c in rule_based_only
    ]
    return decisions


def _load_seen_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def _save_seen_ids(path: Path, seen_ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen_ids)), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=str, default=None, help="Source messages from this CSV pack instead of live Discord (no bot credentials needed)")
    parser.add_argument("--now", type=str, default=None, help="Reference time as 'YYYY-MM-DD HH:MM', --csv mode only (default: latest timestamp in the CSV)")
    parser.add_argument("--send-to-discord", action="store_true", help="Post new candidates to DISCORD_WEBHOOK_URL (.env)")
    args = parser.parse_args()

    webhook_url = None
    if args.send_to_discord:
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            sys.exit("DISCORD_WEBHOOK_URL is not set -- add it to .env (see .env.example) to use --send-to-discord")

    if args.csv:
        messages = load_messages(args.csv)
        now = datetime.strptime(args.now, "%Y-%m-%d %H:%M") if args.now else max(m.created_at for m in messages)
        print(f"Loaded {len(messages)} messages from {args.csv} -- using now = {now:%Y-%m-%d %H:%M}")
        seen_ids_path = CSV_TEST_SEEN_IDS_PATH
    else:
        bot_token = os.environ.get("DISCORD_BOT_TOKEN")
        guild_id = os.environ.get("DISCORD_GUILD_ID")
        channel_ids_raw = os.environ.get("DISCORD_CHANNEL_IDS")
        if not bot_token or not guild_id or not channel_ids_raw:
            sys.exit(
                "DISCORD_BOT_TOKEN, DISCORD_GUILD_ID and DISCORD_CHANNEL_IDS must all be set -- "
                "add them to .env (see .env.example) to use run_live.py"
            )
        channel_ids = [c.strip() for c in channel_ids_raw.split(",") if c.strip()]

        now = datetime.now()
        since = now - timedelta(hours=MIN_HOURS_UNANSWERED + LOOKBACK_SAFETY_MARGIN_HOURS)
        messages = fetch_recent_messages(channel_ids, guild_id, bot_token, since)
        print(f"Fetched {len(messages)} messages from {len(channel_ids)} channel(s) since {since:%Y-%m-%d %H:%M}")
        seen_ids_path = LIVE_SEEN_IDS_PATH

    candidates = find_unanswered_questions(messages, now=now, min_hours_unanswered=MIN_HOURS_UNANSWERED)
    seen_ids = _load_seen_ids(seen_ids_path)
    new_candidates = [c for c in candidates if c.message.msg_id not in seen_ids]
    seen_ids.update(c.message.msg_id for c in candidates)
    _save_seen_ids(seen_ids_path, seen_ids)

    if not new_candidates:
        print("No new candidates this run")
        return

    # Bounded context pool -- graph.py's context-gathering has no upper time
    # bound, so an unbounded `messages` (e.g. the full CSV pack) could dump
    # hundreds of "subsequent messages" into one LLM prompt.
    context_pool = [m for m in messages if now - timedelta(hours=MAX_CONTEXT_HOURS) <= m.created_at <= now]
    decisions = _decide_with_ai_cap(new_candidates, context_pool)
    report = format_report(decisions)
    header = f"=== Live run {now:%Y-%m-%d %H:%M} -- {len(new_candidates)} new ==="
    print(f"{header}\n{report}")

    # AI classification can clear a rule-based candidate (already answered
    # per context) -- only still-open ones get posted, matching
    # format_report's own filtering, which the embed path didn't previously apply.
    still_open = [d for d in decisions if d.still_needs_attention]
    if webhook_url and still_open:
        embeds = [format_candidate_embed(d, MIN_HOURS_UNANSWERED, now) for d in still_open]
        try:
            send_embeds_to_discord(embeds, webhook_url, content=header)
        except RuntimeError as exc:
            sys.exit(f"Failed to post to Discord: {exc}")
        print("\nPosted new candidates to Discord")
    elif webhook_url:
        print("\nAI review cleared all new candidates -- nothing posted to Discord")


if __name__ == "__main__":
    main()
