"""Interactive demo bot: two slash commands people can run live in Discord,
instead of only ever seeing the passive cron output (run_live.py) or the
outbound-only webhook (notify/discord_client.py).

This is the only file in the project that needs a persistent connection to
Discord (the Gateway) rather than a one-shot REST call, so it's the only
one that uses discord.py -- correctly hand-rolling Discord's Gateway
protocol (heartbeats, reconnect/resume) in raw sockets is real protocol
work, unlike the simple urllib calls the rest of the codebase uses.
data/discord_live.py's REST fetch is reused unchanged; discord.py is only
the transport for receiving slash-command interactions.

Must run continuously (unlike main.py/run_live.py, which exit after one
tick) -- discord.py reconnects automatically across network blips, but the
process itself has to keep existing to hold the Gateway connection. See
the plan's Deployment section for systemd / PaaS worker instructions.

Run from the codebase/ directory:

    python3 bot_gateway.py

Requires the same .env as run_live.py: DISCORD_BOT_TOKEN, DISCORD_GUILD_ID,
DISCORD_CHANNEL_IDS. The bot's OAuth2 invite URL must include the
"applications.commands" scope (in addition to "bot") or slash commands
can't be registered -- see .env.example.

Commands sync to DISCORD_GUILD_ID specifically, not globally -- a global
sync can take up to an hour to propagate, which would sink a live demo.

Both commands show the FULL current candidate set on every call, with no
seen_ids dedup -- unlike run_live.py's "only report a question once"
notification flow, an on-demand command should always show "what's true
right now," not "what's new since last time" (which would show nothing
most of the time in a demo).

/labcoach-demo prefers a pre-computed cache (build_demo_cache.py's output,
output/demo_cache/<dataset>.json) over a live call to the graph model, so
repeated demos don't depend on -- or burn through -- the free-tier LLM
quota. Falls back to a live (capped) AI call if no cache exists yet.
/labcoach-check always calls live, since it's checking the real channel.

/labcoach-check uses LIVE_MIN_HOURS_UNANSWERED (default 0.5h, env-overridable)
instead of the production 4h threshold -- a real unanswered question
rarely sits for 4 real hours during a live demo session, so the CSV/cache
path (MIN_HOURS_UNANSWERED, must match build_demo_cache.py's cache) and
the live path are intentionally different constants.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from ai_decide.stub import Decision, decide
from data.discord_live import fetch_recent_messages
from data.loader import load_messages, load_test_case
from detect.rules import explain_detection
from notify.dashboard_log import log_run
from notify.formatter import format_candidate_embed

load_dotenv()  # must run before any os.environ.get() below, or .env-only values are silently ignored

MIN_HOURS_UNANSWERED = 4.0  # /labcoach-demo (CSV path) -- must match build_demo_cache.py's cache, don't change lightly
LIVE_MIN_HOURS_UNANSWERED = float(os.environ.get("LIVE_MIN_HOURS_UNANSWERED", "0.5"))  # /labcoach-check only -- lowered for demo purposes, real messages rarely sit unanswered for a full 4h during a live demo
LOOKBACK_SAFETY_MARGIN_HOURS = 2.0  # matches run_live.py's live-mode lookback
MAX_CONTEXT_HOURS = MIN_HOURS_UNANSWERED + LOOKBACK_SAFETY_MARGIN_HOURS  # bounds the LLM context window
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")  # only GEMINI_API_KEY is configured in .env
# No model_name is passed to decide() -- ai_decide/llm_factory.py already
# resolves the right one per provider (OPENAI_MODEL/GEMINI_MODEL/ANTHROPIC_MODEL,
# see .env.example). Passing one here would hardcode a Gemini-shaped model
# name that breaks if LLM_PROVIDER is ever switched to openai/anthropic.
MAX_AI_REVIEW_PER_CALL = 5  # stay well under the free tier's per-minute quota
DISCORD_PACK_DIR = Path(__file__).resolve().parent.parent / "data" / "discord-pack"
EVAL_TESTCASES_DIR = Path(__file__).resolve().parent.parent / "eval" / "testcases"  # golden set, spec.md §7
DEMO_CACHE_DIR = Path("output/demo_cache")  # built by build_demo_cache.py


def _load_dataset_messages(dataset: str) -> list:
    """Loads a /labcoach-demo dataset by its selected filename -- .json is a
    golden-set case (eval/testcases/, expected_output ignored here, it's
    for the dashboard's comparison view, not the detection/AI pipeline),
    .csv is the plain discord-pack format."""
    if dataset.endswith(".json"):
        messages, _case = load_test_case(EVAL_TESTCASES_DIR / dataset)
        return messages
    return load_messages(DISCORD_PACK_DIR / dataset)


def _load_cached_decisions(dataset: str, candidates: list) -> list[Decision] | None:
    """Loads pre-computed decisions for `dataset` from build_demo_cache.py's
    output, matched back onto the freshly-loaded `candidates` by msg_id.
    Returns None if no cache exists for this dataset (caller falls back to
    a live AI call). A candidate not found in the cache (e.g. the CSV
    changed since the cache was built, or detect/rules.py's filter changed
    and the cache is stale) degrades to rule-based-only, defaulting to NOT
    flagged -- same reasoning as _decide_with_ai_cap's own cap fallback:
    with detection now including every non-bot message, an unreviewed
    default of "needs attention" would flood Discord, not just cover a
    rare edge case."""
    cache_path = DEMO_CACHE_DIR / f"{Path(dataset).stem}.json"
    if not cache_path.exists():
        return None

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    cached_by_id = {d["msg_id"]: d for d in cache["decisions"]}
    decisions = []
    for c in candidates:
        cached = cached_by_id.get(c.message.msg_id)
        if cached is None:
            decisions.append(
                Decision(
                    candidate=c,
                    still_needs_attention=False,
                    confidence=None,
                    rationale="[Rule-based only] Not in demo cache -- rebuild with build_demo_cache.py",
                )
            )
        else:
            decisions.append(
                Decision(
                    candidate=c,
                    still_needs_attention=cached["still_needs_attention"],
                    confidence=cached["confidence"],
                    rationale=cached["rationale"],
                )
            )
    return decisions


def _decide_with_ai_cap(candidates: list, all_messages: list) -> list[Decision]:
    """AI-reviews at most MAX_AI_REVIEW_PER_CALL candidates (oldest-waiting
    first, matching find_unanswered_questions's own sort order) -- the rest
    stay rule-based-only, defaulting to NOT flagged. detect/rules.py now
    only excludes bot messages, so the cap-overflow set is most of every
    message in the channel, not a small handful of genuine candidates --
    defaulting it to "needs attention" (the old behavior) would flood
    Discord with hundreds of embeds per run instead of covering a rare
    edge case."""
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


BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
CHANNEL_IDS_RAW = os.environ.get("DISCORD_CHANNEL_IDS")
if not BOT_TOKEN or not GUILD_ID or not CHANNEL_IDS_RAW:
    raise SystemExit(
        "DISCORD_BOT_TOKEN, DISCORD_GUILD_ID and DISCORD_CHANNEL_IDS must all be set -- "
        "add them to .env (see .env.example) to use bot_gateway.py"
    )
CHANNEL_IDS = [c.strip() for c in CHANNEL_IDS_RAW.split(",") if c.strip()]
GUILD_OBJECT = discord.Object(id=int(GUILD_ID))

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def _ai_source(decision: Decision, used_cache: bool) -> str:
    if decision.rationale.startswith("[Rule-based only] Not in demo cache"):
        return "cache-miss-fallback"
    if decision.rationale.startswith("[Rule-based only]"):
        return "rule-based-cap"
    return "cache" if used_cache else "live-ai"


async def _reply_with_candidates(
    interaction: discord.Interaction,
    messages: list,
    now,
    ephemeral: bool = False,
    cache_dataset: str | None = None,
    min_hours_unanswered: float = MIN_HOURS_UNANSWERED,
    command: str = "labcoach-check",
    source: str = "live",
) -> None:
    run_id = f"{datetime.now():%Y%m%dT%H%M%S%f}"
    record: dict = {
        "run_id": run_id,
        "command": command,
        "source": source,
        "started_at": datetime.now().isoformat(),
        "now": now.isoformat(),
        "fetch": {"message_count": len(messages), "min_hours_unanswered": min_hours_unanswered},
    }

    breakdown = explain_detection(messages, now=now, min_hours_unanswered=min_hours_unanswered)
    candidates = breakdown.candidates
    record["detection_breakdown"] = {
        "total_messages": breakdown.total_messages,
        "bot_messages": breakdown.bot_messages,
        "candidates": len(breakdown.candidates),
    }
    record["candidates"] = [
        {
            "msg_id": c.message.msg_id,
            "channel": c.message.channel,
            "content": c.message.content,
            "hours_since_posted": c.hours_since_posted,
        }
        for c in candidates
    ]
    if not candidates:
        record["ai_review"] = []
        record["posted"] = []
        log_run(record)
        await interaction.followup.send("No unanswered questions right now.", ephemeral=ephemeral)
        return

    used_cache = bool(cache_dataset)
    decisions = _load_cached_decisions(cache_dataset, candidates) if cache_dataset else None
    if decisions is None:
        used_cache = False
        # No cache (or cache_dataset not given, e.g. /labcoach-check against
        # live data) -- bounded context pool, since graph.py's
        # context-gathering has no upper time bound and an unbounded
        # `messages` could dump hundreds of "subsequent messages" into one
        # LLM prompt.
        context_pool = [m for m in messages if now - timedelta(hours=MAX_CONTEXT_HOURS) <= m.created_at <= now]
        decisions = _decide_with_ai_cap(candidates, context_pool)

    record["ai_review"] = [
        {
            "msg_id": d.candidate.message.msg_id,
            "source": _ai_source(d, used_cache),
            "still_needs_attention": d.still_needs_attention,
            "confidence": d.confidence,
            "rationale": d.rationale,
        }
        for d in decisions
    ]

    # AI classification can clear a rule-based candidate (already answered per
    # context) -- only still-open ones get posted, matching format_report's
    # own filtering, which the embed path didn't previously apply.
    decisions = [d for d in decisions if d.still_needs_attention]
    record["posted"] = [d.candidate.message.msg_id for d in decisions]
    if not decisions:
        log_run(record)
        await interaction.followup.send(
            "No unanswered questions right now (AI review cleared all rule-based candidates).",
            ephemeral=ephemeral,
        )
        return

    log_run(record)
    embeds = [
        discord.Embed.from_dict(format_candidate_embed(d, min_hours_unanswered, now)) for d in decisions
    ]
    # Discord caps a single message at 10 embeds -- send in batches if needed.
    for i in range(0, len(embeds), 10):
        await interaction.followup.send(embeds=embeds[i : i + 10], ephemeral=ephemeral)


THRESHOLD_CHOICES = [
    app_commands.Choice(name="30 minutes", value=30),
    app_commands.Choice(name="1 hour", value=60),
    app_commands.Choice(name="2 hours", value=120),
    app_commands.Choice(name="4 hours", value=240),
]


@tree.command(
    name="labcoach-check",
    description="Check the real Discord channel right now for unanswered questions",
    guild=GUILD_OBJECT,
)
@app_commands.describe(threshold="How long unanswered before it's flagged (default: LIVE_MIN_HOURS_UNANSWERED in .env)")
@app_commands.choices(threshold=THRESHOLD_CHOICES)
async def labcoach_check(interaction: discord.Interaction, threshold: app_commands.Choice[int] | None = None) -> None:
    await interaction.response.defer()
    min_hours = threshold.value / 60 if threshold is not None else LIVE_MIN_HOURS_UNANSWERED
    now = datetime.now()
    since = now - timedelta(hours=min_hours + LOOKBACK_SAFETY_MARGIN_HOURS)
    messages = fetch_recent_messages(CHANNEL_IDS, GUILD_ID, BOT_TOKEN, since)
    await _reply_with_candidates(
        interaction, messages, now, min_hours_unanswered=min_hours, command="labcoach-check", source="live"
    )


async def _dataset_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    csv_files = sorted(p.name for p in DISCORD_PACK_DIR.glob("*.csv"))
    case_files = sorted(p.name for p in EVAL_TESTCASES_DIR.glob("*.json"))
    names = csv_files + case_files
    return [
        app_commands.Choice(name=name, value=name) for name in names if current.lower() in name.lower()
    ][:25]  # Discord's autocomplete result cap


@tree.command(
    name="labcoach-demo",
    description="Run the unanswered-question check against a sample data pack or eval/testcases golden-set case",
    guild=GUILD_OBJECT,
)
@app_commands.describe(dataset="Which sample CSV or eval/testcases case (.json) to run against", private="Only show the result to you (default: public)")
@app_commands.autocomplete(dataset=_dataset_autocomplete)
async def labcoach_demo(interaction: discord.Interaction, dataset: str, private: bool = False) -> None:
    await interaction.response.defer(ephemeral=private)
    dataset_path = (EVAL_TESTCASES_DIR if dataset.endswith(".json") else DISCORD_PACK_DIR) / dataset
    if not dataset_path.exists():
        await interaction.followup.send(f"No such dataset: {dataset}", ephemeral=private)
        return

    messages = _load_dataset_messages(dataset)
    now = max(m.created_at for m in messages)
    await _reply_with_candidates(
        interaction, messages, now, ephemeral=private, cache_dataset=dataset, command="labcoach-demo", source=dataset
    )


MAX_CSV_PREVIEW_ROWS = 25
CSV_PREVIEW_CONTENT_WIDTH = 200  # column-width truncation for table readability, not the citation rule's 2-sentence limit


@tree.command(
    name="labcoach-csv-preview",
    description="Privately preview raw rows from a sample data pack (only visible to you)",
    guild=GUILD_OBJECT,
)
@app_commands.describe(
    dataset="Which sample CSV or eval/testcases case (.json) to preview",
    rows=f"How many rows to show (default 10, max {MAX_CSV_PREVIEW_ROWS})",
    offset="Skip this many rows first, to page through the file",
)
@app_commands.autocomplete(dataset=_dataset_autocomplete)
async def labcoach_csv_preview(
    interaction: discord.Interaction, dataset: str, rows: int = 10, offset: int = 0
) -> None:
    await interaction.response.defer(ephemeral=True)
    dataset_path = (EVAL_TESTCASES_DIR if dataset.endswith(".json") else DISCORD_PACK_DIR) / dataset
    if not dataset_path.exists():
        await interaction.followup.send(f"No such dataset: {dataset}", ephemeral=True)
        return

    rows = max(1, min(rows, MAX_CSV_PREVIEW_ROWS))
    offset = max(0, offset)
    messages = _load_dataset_messages(dataset)
    page = messages[offset : offset + rows]
    if not page:
        await interaction.followup.send(f"No rows at offset {offset} (dataset has {len(messages)} total).", ephemeral=True)
        return

    lines = []
    for m in page:
        content = m.content[:CSV_PREVIEW_CONTENT_WIDTH]
        if len(m.content) > CSV_PREVIEW_CONTENT_WIDTH:
            content += "..."
        lines.append(f"{m.msg_id} | {m.author} | {m.created_at:%Y-%m-%d %H:%M} | {m.channel} | {content}")

    header = f"Rows {offset}-{offset + len(page) - 1} of {len(messages)} in {dataset}:"
    # A full page of long rows can exceed Discord's 2000-char message cap --
    # chunk onto code-block boundaries rather than assume it always fits.
    # The first chunk also carries the header line, so it gets less budget.
    fence_overhead = len("```\n\n```")
    budget = 2000 - fence_overhead - len(header) - 1
    chunks: list[list[str]] = [[]]
    chunk_len = 0
    for line in lines:
        if chunk_len + len(line) + 1 > budget and chunks[-1]:
            chunks.append([])
            chunk_len = 0
        chunks[-1].append(line)
        chunk_len += len(line) + 1

    await interaction.followup.send(f"{header}\n```\n{chr(10).join(chunks[0])}\n```", ephemeral=True)
    for chunk in chunks[1:]:
        await interaction.followup.send(f"```\n{chr(10).join(chunk)}\n```", ephemeral=True)


@client.event
async def on_ready() -> None:
    await tree.sync(guild=GUILD_OBJECT)
    print(f"Logged in as {client.user} -- commands synced to guild {GUILD_ID}")


if __name__ == "__main__":
    client.run(BOT_TOKEN)
