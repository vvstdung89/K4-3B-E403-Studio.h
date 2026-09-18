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

Both commands classify the full candidate batch with the configured model.
The dashboard may separately replay a locally generated demo cache.

/labcoach-check uses LIVE_MIN_HOURS_UNANSWERED (default 0.5h, env-overridable)
instead of the production 4h threshold -- a real unanswered question
rarely sits for 4 real hours during a live demo session, so the CSV/cache
path (MIN_HOURS_UNANSWERED, must match build_demo_cache.py's cache) and
the live path are intentionally different constants.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from ai_decide.stub import decide
from data.discord_live import ALL_HISTORY_SINCE, fetch_recent_messages
from detect.rules import explain_detection
from notify.dashboard_log import log_run, mark_resolved
from notify.formatter import format_candidate_embed
from pipeline_common import (
    DISCORD_PACK_DIR,
    EVAL_TESTCASES_DIR,
    LIVE_SEEN_IDS_PATH,
    LOOKBACK_SAFETY_MARGIN_HOURS,
    MIN_HOURS_UNANSWERED,
    load_dataset_messages as _load_dataset_messages,
    load_seen_ids,
    save_seen_ids,
)

load_dotenv()  # must run before any os.environ.get() below, or .env-only values are silently ignored

LIVE_MIN_HOURS_UNANSWERED = float(os.environ.get("LIVE_MIN_HOURS_UNANSWERED", "0.5"))  # /labcoach-check only -- lowered for demo purposes, real messages rarely sit unanswered for a full 4h during a live demo
MAX_CONTEXT_HOURS = MIN_HOURS_UNANSWERED + LOOKBACK_SAFETY_MARGIN_HOURS  # bounds the LLM context window
LIVE_CHECK_INTERVAL_MINUTES = float(os.environ.get("LIVE_CHECK_INTERVAL_MINUTES", "30"))  # auto_check_live's cadence

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


def _build_action_view(m, guild_id: str) -> discord.ui.View:
    """One message's button row: a Link-style "jump to message" button (no
    interaction routing needed -- Discord opens the URL client-side) plus a
    "Mark Solved" button whose callback is assigned directly on the Button
    instance. That's the discord.py pattern that coexists safely with
    app_commands.CommandTree -- overriding Client.on_interaction instead
    would risk shadowing the tree's own slash-command dispatch.

    Built fresh per message with a dynamic custom_id (labcoach:resolve:<msg_id>)
    and lives only in memory for this process's lifetime -- if bot_gateway.py
    restarts, buttons on older messages stop working (no persistent-view
    registration for arbitrarily many dynamic ids). Acceptable for now."""
    view = discord.ui.View(timeout=None)
    link = f"https://discord.com/channels/{guild_id}/{m.channel}/{m.msg_id}"
    view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, url=link, label="Jump to message"))

    resolve_btn = discord.ui.Button(
        style=discord.ButtonStyle.success, label="Mark Solved", custom_id=f"labcoach:resolve:{m.msg_id}"
    )

    async def _on_resolve(interaction: discord.Interaction) -> None:
        resolver = str(interaction.user)
        mark_resolved(m.msg_id, resolved_by=resolver)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.add_field(name="✅ Đã xử lý", value=f"Resolved by {resolver}", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)

    resolve_btn.callback = _on_resolve
    view.add_item(resolve_btn)
    return view


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

    decisions = decide(candidates, all_messages=messages)
    record["ai_review"] = [
        {
            "msg_id": d.candidate.message.msg_id,
            "source": "live-ai",
            "still_needs_attention": d.still_needs_attention,
            "confidence": d.confidence,
            "rationale": d.rationale,
        }
        for d in decisions
    ]
    decisions = [d for d in decisions if d.still_needs_attention]
    record["posted"] = [d.candidate.message.msg_id for d in decisions]
    log_run(record)
    if not decisions:
        await interaction.followup.send(
            "No unanswered questions right now (AI review cleared all candidates).",
            ephemeral=ephemeral,
        )
        return
    if source == "live":
        # One message per candidate -- buttons attach to the whole message,
        # not to an individual embed within it, so a per-candidate "Mark
        # Solved" button needs its own message.
        for d in decisions:
            embed = discord.Embed.from_dict(
                format_candidate_embed(d, min_hours_unanswered, now, interactive=True)
            )
            view = _build_action_view(d.candidate.message, GUILD_ID)
            await interaction.followup.send(embed=embed, view=view, ephemeral=ephemeral)
        return

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
@app_commands.describe(
    threshold="How long unanswered before it's flagged (default: LIVE_MIN_HOURS_UNANSWERED in .env)",
    all_messages="Fetch the channel's entire history instead of just the recent lookback window",
)
@app_commands.choices(threshold=THRESHOLD_CHOICES)
async def labcoach_check(
    interaction: discord.Interaction, threshold: app_commands.Choice[int] | None = None, all_messages: bool = False
) -> None:
    await interaction.response.defer()
    min_hours = threshold.value / 60 if threshold is not None else LIVE_MIN_HOURS_UNANSWERED
    now = datetime.now()
    since = ALL_HISTORY_SINCE if all_messages else now - timedelta(hours=min_hours + LOOKBACK_SAFETY_MARGIN_HOURS)
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


@tasks.loop(minutes=LIVE_CHECK_INTERVAL_MINUTES)
async def auto_check_live() -> None:
    """Unattended counterpart to /labcoach-check -- runs on a timer instead of
    a slash command, using the production MIN_HOURS_UNANSWERED threshold (not
    LIVE_MIN_HOURS_UNANSWERED's demo-lowered value), deduping against the same
    disk-persisted seen_ids run_live.py uses so a still-unanswered question
    isn't reposted every tick. Posts via the bot's own channel.send() (not a
    webhook -- a plain incoming webhook can't host a working "Mark Solved"
    button, see _build_action_view), one message per still-open candidate,
    into that candidate's own originating channel."""
    now = datetime.now()
    since = now - timedelta(hours=MIN_HOURS_UNANSWERED + LOOKBACK_SAFETY_MARGIN_HOURS)
    messages = fetch_recent_messages(CHANNEL_IDS, GUILD_ID, BOT_TOKEN, since)

    run_id = f"{datetime.now():%Y%m%dT%H%M%S%f}"
    record: dict = {
        "run_id": run_id,
        "command": "labcoach-auto",
        "source": "live",
        "started_at": datetime.now().isoformat(),
        "now": now.isoformat(),
        "fetch": {"message_count": len(messages), "min_hours_unanswered": MIN_HOURS_UNANSWERED},
    }

    breakdown = explain_detection(messages, now=now, min_hours_unanswered=MIN_HOURS_UNANSWERED)
    seen_ids = load_seen_ids(LIVE_SEEN_IDS_PATH)
    new_candidates = [c for c in breakdown.candidates if c.message.msg_id not in seen_ids]
    seen_ids.update(c.message.msg_id for c in breakdown.candidates)
    save_seen_ids(LIVE_SEEN_IDS_PATH, seen_ids)

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
        for c in new_candidates
    ]
    if not new_candidates:
        record["ai_review"] = []
        record["posted"] = []
        log_run(record)
        return

    decisions = decide(new_candidates, all_messages=messages)
    record["ai_review"] = [
        {
            "msg_id": d.candidate.message.msg_id,
            "source": "live-ai",
            "still_needs_attention": d.still_needs_attention,
            "confidence": d.confidence,
            "rationale": d.rationale,
        }
        for d in decisions
    ]
    still_open = [d for d in decisions if d.still_needs_attention]
    record["posted"] = [d.candidate.message.msg_id for d in still_open]
    log_run(record)
    for d in still_open:
        m = d.candidate.message
        embed = discord.Embed.from_dict(format_candidate_embed(d, MIN_HOURS_UNANSWERED, now, interactive=True))
        view = _build_action_view(m, GUILD_ID)
        try:
            channel = client.get_channel(int(m.channel)) or await client.fetch_channel(int(m.channel))
            await channel.send(embed=embed, view=view)
        except discord.DiscordException as exc:
            print(f"[auto_check_live] Failed to post to channel {m.channel}: {exc}")


@client.event
async def on_ready() -> None:
    await tree.sync(guild=GUILD_OBJECT)
    print(f"Logged in as {client.user} -- commands synced to guild {GUILD_ID}")
    if not auto_check_live.is_running():
        auto_check_live.start()


if __name__ == "__main__":
    client.run(BOT_TOKEN)
