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
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from ai_decide.stub import decide
from data.discord_live import fetch_recent_messages
from data.loader import load_messages
from detect.rules import find_unanswered_questions
from notify.formatter import format_candidate_embed

MIN_HOURS_UNANSWERED = 4.0  # matches detect.rules.find_unanswered_questions's default
LOOKBACK_SAFETY_MARGIN_HOURS = 2.0  # matches run_live.py's live-mode lookback
DISCORD_PACK_DIR = Path(__file__).resolve().parent.parent / "data" / "discord-pack"

load_dotenv()

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


async def _reply_with_candidates(interaction: discord.Interaction, messages: list, now, ephemeral: bool = False) -> None:
    candidates = find_unanswered_questions(messages, now=now, min_hours_unanswered=MIN_HOURS_UNANSWERED)
    if not candidates:
        await interaction.followup.send("No unanswered questions right now.", ephemeral=ephemeral)
        return

    decisions = decide(candidates, all_messages=messages)
    embeds = [
        discord.Embed.from_dict(format_candidate_embed(d, MIN_HOURS_UNANSWERED, now)) for d in decisions
    ]
    # Discord caps a single message at 10 embeds -- send in batches if needed.
    for i in range(0, len(embeds), 10):
        await interaction.followup.send(embeds=embeds[i : i + 10], ephemeral=ephemeral)


@tree.command(
    name="labcoach-check",
    description="Check the real Discord channel right now for unanswered questions",
    guild=GUILD_OBJECT,
)
async def labcoach_check(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    now = datetime.now()
    since = now - timedelta(hours=MIN_HOURS_UNANSWERED + LOOKBACK_SAFETY_MARGIN_HOURS)
    messages = fetch_recent_messages(CHANNEL_IDS, GUILD_ID, BOT_TOKEN, since)
    await _reply_with_candidates(interaction, messages, now)


async def _dataset_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    csv_files = sorted(p.name for p in DISCORD_PACK_DIR.glob("*.csv"))
    return [
        app_commands.Choice(name=name, value=name) for name in csv_files if current.lower() in name.lower()
    ][:25]  # Discord's autocomplete result cap


@tree.command(
    name="labcoach-demo",
    description="Run the unanswered-question check against a sample data pack",
    guild=GUILD_OBJECT,
)
@app_commands.describe(dataset="Which sample CSV to run against", private="Only show the result to you (default: public)")
@app_commands.autocomplete(dataset=_dataset_autocomplete)
async def labcoach_demo(interaction: discord.Interaction, dataset: str, private: bool = False) -> None:
    await interaction.response.defer(ephemeral=private)
    csv_path = DISCORD_PACK_DIR / dataset
    if not csv_path.exists():
        await interaction.followup.send(f"No such dataset: {dataset}", ephemeral=private)
        return

    messages = load_messages(csv_path)
    now = max(m.created_at for m in messages)
    await _reply_with_candidates(interaction, messages, now, ephemeral=private)


MAX_CSV_PREVIEW_ROWS = 25
CSV_PREVIEW_CONTENT_WIDTH = 200  # column-width truncation for table readability, not the citation rule's 2-sentence limit


@tree.command(
    name="labcoach-csv-preview",
    description="Privately preview raw rows from a sample data pack (only visible to you)",
    guild=GUILD_OBJECT,
)
@app_commands.describe(
    dataset="Which sample CSV to preview",
    rows=f"How many rows to show (default 10, max {MAX_CSV_PREVIEW_ROWS})",
    offset="Skip this many rows first, to page through the file",
)
@app_commands.autocomplete(dataset=_dataset_autocomplete)
async def labcoach_csv_preview(
    interaction: discord.Interaction, dataset: str, rows: int = 10, offset: int = 0
) -> None:
    await interaction.response.defer(ephemeral=True)
    csv_path = DISCORD_PACK_DIR / dataset
    if not csv_path.exists():
        await interaction.followup.send(f"No such dataset: {dataset}", ephemeral=True)
        return

    rows = max(1, min(rows, MAX_CSV_PREVIEW_ROWS))
    offset = max(0, offset)
    messages = load_messages(csv_path)
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
