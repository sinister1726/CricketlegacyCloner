"""
Custom team names — if enabled in /settings, both captains are DM'd after
captain selection to pick a name for their team.

Flow:
  1. ask_team_names(client, match, capA_uid, capB_uid) called from setup.py
  2. Both captains are DM'd simultaneously (non-blocking via asyncio.create_task)
  3. Each captain has 45 s to reply in the bot's DM with a name (max 20 chars)
  4. Names saved into match["teams"]["A/B"]["name"]
  5. Helper get_team_name(match, team_key) returns the name or default "Team A/B"
"""

import asyncio
import html
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from plugins.game.team import ACTIVE_MATCHES

# uid → asyncio.Future (resolved with the name string)
PENDING_NAMES: dict = {}

_MAX_LEN   = 20
_WAIT_SECS = 45


def get_team_name(match: dict, team_key: str) -> str:
    """Return custom name if set, otherwise 'Team A' / 'Team B'."""
    return (
        match.get("teams", {}).get(team_key, {}).get("name")
        or f"Team {team_key}"
    )


async def _ask_one_captain(client, cap_uid: int, team_key: str, chat_id: int):
    """DM one captain asking for a team name. Resolves via PENDING_NAMES future."""
    loop   = asyncio.get_event_loop()
    future = loop.create_future()
    PENDING_NAMES[cap_uid] = future

    try:
        await client.send_message(
            cap_uid,
            (
                f"🏷 <b>Name Your Team!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"You are captaining <b>Team {team_key}</b>.\n"
                f"Send your team name here within <b>{_WAIT_SECS}s</b>.\n"
                f"<i>(Max {_MAX_LEN} characters. Skipped if you don't reply.)</i>"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        PENDING_NAMES.pop(cap_uid, None)
        return None

    try:
        name = await asyncio.wait_for(
            asyncio.shield(future), timeout=_WAIT_SECS
        )
        return name
    except asyncio.TimeoutError:
        return None
    finally:
        PENDING_NAMES.pop(cap_uid, None)


async def ask_team_names(client, match: dict, capA_uid: int, capB_uid: int):
    """
    Concurrently ask both captains for their team names.
    Called from setup.py as a background task — does not block match flow.
    """
    name_a, name_b = await asyncio.gather(
        _ask_one_captain(client, capA_uid, "A", match["chat_id"]),
        _ask_one_captain(client, capB_uid, "B", match["chat_id"]),
    )

    chat_id = match["chat_id"]
    match   = ACTIVE_MATCHES.get(chat_id, match)   # re-fetch in case ref changed

    if name_a:
        match["teams"]["A"]["name"] = name_a
    if name_b:
        match["teams"]["B"]["name"] = name_b

    if name_a or name_b:
        na = html.escape(name_a or "Team A")
        nb = html.escape(name_b or "Team B")
        try:
            await client.send_message(
                chat_id,
                (
                    "🏷 <b>Team Names Set!</b>\n"
                    f"🌊 <b>{na}</b>  vs  🔥 <b>{nb}</b>"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


# ── DM handler ────────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.text, group=4)
async def team_name_dm_handler(client: Client, message: Message):
    uid = message.from_user.id

    future = PENDING_NAMES.get(uid)
    if future is None or future.done():
        return

    raw  = message.text.strip()
    # strip markdown/html
    name = raw[:_MAX_LEN].strip()

    if not name:
        return await message.reply_text(
            "⚠️ Name can't be empty. Try again.",
            parse_mode=ParseMode.HTML,
        )

    future.set_result(name)
    PENDING_NAMES.pop(uid, None)

    await message.reply_text(
        f"✅ <b>Team name set to:</b> <b>{html.escape(name)}</b>",
        parse_mode=ParseMode.HTML,
    )
    await message.stop_propagation()
