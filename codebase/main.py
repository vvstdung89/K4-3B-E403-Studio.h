"""CSV demo entry point: load -> detect -> batch AI decision -> notify.

Run from the codebase/ directory:

    python3 main.py
    python3 main.py --save          # also writes codebase/output/report.md
    python3 main.py --now "2026-09-13 12:00"   # override the reference clock
    python3 main.py --send-to-discord           # also posts the report to
                                                  # DISCORD_WEBHOOK_URL (.env)

Install requirements.txt and configure the LLM provider in codebase/.env.
Non-empty candidate batches call the configured model even without
--send-to-discord; that flag additionally posts the report to Discord.
Model errors keep candidates for manual review. Traces go to codebase/logs/;
--save writes output/report.md. The source data is read-only.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

from ai_decide.stub import decide
from data.loader import default_csv_path, load_messages
from detect.rules import find_unanswered_questions
from notify.discord_client import send_to_discord
from notify.formatter import format_report, write_report


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=str, default=None, help="Path to k4_messages.csv (default: data/discord-pack/)")
    parser.add_argument("--now", type=str, default=None, help="Reference time as 'YYYY-MM-DD HH:MM' (default: latest message timestamp in the pack)")
    parser.add_argument("--save", action="store_true", help="Also write the report to codebase/output/report.md")
    parser.add_argument("--send-to-discord", action="store_true", help="Post the report to DISCORD_WEBHOOK_URL (.env)")
    args = parser.parse_args()

    messages = load_messages(args.csv)
    n_bot = sum(1 for m in messages if m.is_bot)
    print(f"Loaded {len(messages)} messages ({len(messages) - n_bot} human, {n_bot} bot) from {args.csv or default_csv_path().name}")

    if args.now:
        now = datetime.strptime(args.now, "%Y-%m-%d %H:%M")
    else:
        # Default to the latest timestamp IN the dataset, not wall-clock time:
        # this is a static 2026-09-12..14 pack, so datetime.now() would put
        # every message trivially past the 4h threshold and defeat the demo.
        now = max(m.created_at for m in messages)
    print(f"Using now = {now:%Y-%m-%d %H:%M} for the unanswered-question threshold")

    candidates = find_unanswered_questions(messages, now=now)
    print(f"Found {len(candidates)} non-bot candidate(s) for AI review")

    print("AI step: LangGraph batch classify (one LLM call for the candidate list)")
    decisions = decide(candidates, all_messages=messages)

    report = format_report(decisions)
    print()
    print(report)

    if args.save:
        out_path = "output/report.md"
        write_report(report, out_path)
        print(f"\nSaved report to {out_path}")

    if args.send_to_discord:
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            sys.exit("DISCORD_WEBHOOK_URL is not set -- add it to .env (see .env.example) to use --send-to-discord")
        try:
            send_to_discord(report, webhook_url)
        except RuntimeError as exc:
            sys.exit(f"Failed to post report to Discord: {exc}")
        print("\nPosted report to Discord")


if __name__ == "__main__":
    main()
