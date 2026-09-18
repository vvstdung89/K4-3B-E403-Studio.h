"""Fetches messages from a real Discord server via the Bot REST API.

The `data/loader.py`-anticipated live counterpart to the static CSV pack:
this module is the only one that knows Discord's message JSON shape.
Everything downstream (detect/, ai_decide/, notify/) still only ever sees
the same `Message` dataclass loader.py produces, so no other module needs
to change to switch data sources -- see run_live.py for the swap.

Requires a real Discord Bot application (not the webhook used for outbound
delivery in notify/discord_client.py): a bot token, invited to the target
server with "View Channel" + "Read Message History" permissions, and
"Message Content Intent" enabled in the Developer Portal (Bot tab) --
without that intent Discord silently returns empty `content` fields.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from data.loader import Message

DISCORD_API = "https://discord.com/api/v10"
DISCORD_EPOCH_MS = 1420070400000  # 2015-01-01T00:00:00Z, per Discord's snowflake spec
VN_OFFSET = timezone(timedelta(hours=7))
PAGE_LIMIT = 100
ALL_HISTORY_SINCE = datetime(2015, 1, 1, tzinfo=timezone.utc)  # Discord's epoch (UTC) -- pass as `since` to fetch a
# channel's entire history. Must stay tz-aware: _snowflake_from_datetime's `dt.timestamp()` interprets a naive
# datetime as local system time, so on a UTC+ system a naive 2015-01-01 converts to a moment before the real UTC
# epoch, producing a negative (Discord API-rejected) snowflake -- confirmed by testing on this VN (+7) machine.


def _get(url: str, bot_token: str) -> list | dict:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bot {bot_token}",
            # Same Cloudflare block notify/discord_client.py hit on the
            # webhook path -- the default urllib User-Agent gets a 403 here too.
            "User-Agent": "LabCoach-Bot/1.0",
        },
        method="GET",
    )
    while True:
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = float(exc.headers.get("Retry-After", "1"))
                time.sleep(retry_after)
                continue
            raise RuntimeError(f"Discord API GET failed: {exc.code} {exc.reason} ({url})") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Discord API GET failed: {exc.reason} ({url})") from exc


def _fetch_bot_user_id(bot_token: str) -> str:
    me = _get(f"{DISCORD_API}/users/@me", bot_token)
    return me["id"]


def _snowflake_from_datetime(dt: datetime) -> str:
    """Builds a Discord snowflake ID that sorts as "created at dt", so it
    can be used directly as an `after=` cursor -- no separate "last seen
    message id" needs to be tracked just to know where to start fetching."""
    unix_ms = int(dt.timestamp() * 1000)
    return str((unix_ms - DISCORD_EPOCH_MS) << 22)


def _fetch_channel_messages(channel_id: str, bot_token: str, after: str) -> list[dict]:
    """Pages forward from `after` until a page returns fewer than
    PAGE_LIMIT messages -- an active channel's lookback window would
    otherwise be silently truncated at 100 messages."""
    all_raw: list[dict] = []
    cursor = after
    while True:
        page = _get(f"{DISCORD_API}/channels/{channel_id}/messages?limit={PAGE_LIMIT}&after={cursor}", bot_token)
        if not page:
            break
        all_raw.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        cursor = max(page, key=lambda m: int(m["id"]))["id"]
    return all_raw


def _to_message(raw: dict, channel_id: str, guild_id: str, bot_user_id: str) -> Message:
    """Maps one Discord API message object to the same Message dataclass
    data/loader.py produces from a CSV row.

    SAFETY: `author` is the raw Discord user id, kept for internal routing
    only -- same rule as loader.py's CSV-sourced `author`, never surface it
    in a report (see notify/formatter.py's placeholder Học viên field).

    Discord's `timestamp` is tz-aware UTC-offset ISO8601; loader.py's
    `created_at` is naive VN-local (from the CSV's `created_at_vn` column).
    Converting here keeps `now - m.created_at` in detect/rules.py valid --
    subtracting a naive datetime from an aware one raises, and skipping the
    UTC->VN shift would silently misalign every threshold check by 7h.
    """
    created_at_utc = datetime.fromisoformat(raw["timestamp"])
    created_at_vn = created_at_utc.astimezone(VN_OFFSET).replace(tzinfo=None)

    reply_to = None
    ref = raw.get("message_reference")
    if ref:
        reply_to = ref.get("message_id")

    mention_ids = {u["id"] for u in raw.get("mentions", [])}

    return Message(
        msg_id=raw["id"],
        guild=guild_id,
        channel=channel_id,
        author=raw["author"]["id"],
        is_bot=raw["author"].get("bot", False),
        msg_type="reply" if reply_to else "message",
        created_at=created_at_vn,
        reply_to=reply_to,
        mentions_bot=bot_user_id in mention_ids,
        n_attachments=len(raw.get("attachments", [])),
        n_chars=len(raw.get("content", "")),
        content=raw.get("content", ""),
    )


def fetch_recent_messages(channel_ids: list[str], guild_id: str, bot_token: str, since: datetime) -> list[Message]:
    """Fetches every message newer than `since` across `channel_ids`,
    converted to the same Message type load_messages() returns.

    `since` should reach back at least detect.rules.find_unanswered_questions's
    min_hours_unanswered (plus a safety margin) -- not just the cron tick
    interval -- so a question that's already hours old is still visible to
    the threshold check, and any reply to it that also falls in the window
    is visible too (find_unanswered_questions excludes replied-to messages
    on its own; it just needs both message and reply in the fetched set).
    """
    bot_user_id = _fetch_bot_user_id(bot_token)
    after = _snowflake_from_datetime(since)

    messages: list[Message] = []
    for channel_id in channel_ids:
        for raw in _fetch_channel_messages(channel_id, bot_token, after):
            messages.append(_to_message(raw, channel_id, guild_id, bot_user_id))

    messages.sort(key=lambda m: m.created_at)
    return messages
