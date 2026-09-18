"""Simulates the flowchart's 30-minute cron cycle (outputs/workflow.jpg,
steps 1-5) against the static k4_messages.csv pack: a fast historical
replay, not a real scheduler -- see main.py's docstring for why
datetime.now() can't be used with this static 2026-09-12..14 pack.

Run from the codebase/ directory:

    python3 simulate_cron.py                      # dry run, prints each tick's new candidates
    python3 simulate_cron.py --send-to-discord     # also posts each tick's new candidates
    python3 simulate_cron.py --save                # also writes output/sim/tick_*.md
    python3 simulate_cron.py --tick-minutes 15     # override cron interval (default 30)

Each tick reuses find_unanswered_questions() with the existing 4h threshold
(detect/rules.py) -- the 30-minute cadence only controls how often the check
runs, not the surfacing threshold. A message is reported on the FIRST tick
where it appears (the tick after it crosses 4h old), never again on later
ticks -- otherwise a still-open question would be re-posted every 30 minutes
for as long as it stays unanswered.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

from ai_decide.stub import decide
from data.loader import default_csv_path, load_messages
from detect.rules import find_unanswered_questions
from notify.discord_client import send_embeds_to_discord
from notify.formatter import format_candidate_embed, format_report, write_report
from pipeline_common import LOOKBACK_SAFETY_MARGIN_HOURS, MIN_HOURS_UNANSWERED

load_dotenv()  # must run before any os.environ.get() below, or .env-only values are silently ignored

MAX_CONTEXT_HOURS = MIN_HOURS_UNANSWERED + LOOKBACK_SAFETY_MARGIN_HOURS  # bounds the LLM context window per tick


def _tick_range(messages, tick_minutes: int) -> list[datetime]:
    timestamps = [m.created_at for m in messages]
    start = min(timestamps)
    start -= timedelta(minutes=start.minute % tick_minutes, seconds=start.second, microseconds=start.microsecond)
    end = max(timestamps)

    ticks = []
    t = start
    while t <= end:
        ticks.append(t)
        t += timedelta(minutes=tick_minutes)
    if not ticks or ticks[-1] < end:
        ticks.append(end)
    return ticks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=str, default=None, help="Path to k4_messages.csv (default: data/discord-pack/)")
    parser.add_argument("--tick-minutes", type=int, default=30, help="Simulated cron interval in minutes (default: 30)")
    parser.add_argument("--save", action="store_true", help="Also write output/sim/tick_<timestamp>.md per non-empty tick")
    parser.add_argument("--send-to-discord", action="store_true", help="Post each tick's new candidates to DISCORD_WEBHOOK_URL (.env)")
    args = parser.parse_args()

    messages = load_messages(args.csv)
    print(f"Loaded {len(messages)} messages from {args.csv or default_csv_path().name}")

    webhook_url = None
    if args.send_to_discord:
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            sys.exit("DISCORD_WEBHOOK_URL is not set -- add it to .env (see .env.example) to use --send-to-discord")

    ticks = _tick_range(messages, args.tick_minutes)
    print(
        f"Simulating {len(ticks)} cron ticks every {args.tick_minutes}min "
        f"from {ticks[0]:%Y-%m-%d %H:%M} to {ticks[-1]:%Y-%m-%d %H:%M}\n"
    )

    seen_ids: set[str] = set()
    for tick in ticks:
        candidates = find_unanswered_questions(messages, now=tick, min_hours_unanswered=MIN_HOURS_UNANSWERED)
        new_candidates = [c for c in candidates if c.message.msg_id not in seen_ids]
        seen_ids.update(c.message.msg_id for c in candidates)
        if not new_candidates:
            continue

        decisions = decide(new_candidates, all_messages=messages)
        report = format_report(decisions)
        header = f"=== Cron tick {tick:%Y-%m-%d %H:%M} -- {len(new_candidates)} new ==="
        print(f"{header}\n{report}\n")

        if args.save:
            out_path = f"output/sim/tick_{tick:%Y%m%d_%H%M}.md"
            write_report(report, out_path)

        # AI classification can clear a rule-based candidate (already
        # answered per context) -- only still-open ones get posted, matching
        # format_report's own filtering, which the embed path didn't
        # previously apply.
        still_open = [d for d in decisions if d.still_needs_attention]
        if webhook_url and still_open:
            embeds = [format_candidate_embed(d, MIN_HOURS_UNANSWERED, tick) for d in still_open]
            try:
                send_embeds_to_discord(embeds, webhook_url, content=header)
            except RuntimeError as exc:
                sys.exit(f"Failed to post tick {tick:%Y-%m-%d %H:%M} to Discord: {exc}")

    print(f"Done -- {len(seen_ids)} total candidate(s) surfaced across {len(ticks)} ticks")


if __name__ == "__main__":
    main()
