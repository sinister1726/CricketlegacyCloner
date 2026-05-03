"""Group game entry: `/start` (and aliases `/play`, `/newgame`) open the
mode picker — Team / Solo / 1v1 Duel.

Flow:
  • If the user is a group admin/owner → skip voting, show mode picker directly.
  • Otherwise → show a voting dialogue (image + Vote button).
    – 3 unique votes → proceed to mode picker.
    – 2-minute timeout with < 3 votes → expire and delete the dialogue.

When global maintenance mode is ON, the maintenance gate in
`plugins/admin/maintenance.py` intercepts these commands before this runs.
"""

import asyncio

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)

from Assets.files import START_IMAGE_GROUP
from database.games import is_game_active

# ── constants ────────────────────────────────────────────────────────────────

VOTE_IMAGE = "https://graph.org/file/82fa7ec61ef263e7fc5ea-93eb782dc413885a2c.jpg"
VOTES_REQUIRED = 3
VOTE_TIMEOUT = 120  # seconds

# ── in-memory vote state ──────────────────────────────────────────────────────
# chat_id → {initiator_id, initiator_name, voters: set, message, task}
VOTE_STATE: dict = {}

# ── mode picker ───────────────────────────────────────────────────────────────

PICKER_CAPTION = (
    "🎮 <b>SELECT MODE</b>\n"
    "──┈┄┄╌╌╌╌┄┄┈──\n"
    "Choose how you want to play 👇\n\n"
    "⚔️ <i>1v1 Duel runs in the bot DM — tap to queue.</i>"
)


def _mode_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏏 Team", callback_data="mode_team"),
                InlineKeyboardButton("👤 Solo", callback_data="mode_solo"),
            ],
            [
                InlineKeyboardButton("⚔️ 1v1 Duel", callback_data="mode_duel"),
            ],
            [InlineKeyboardButton("✖ Cancel", callback_data="mode_cancel")],
        ]
    )


# ── helpers ───────────────────────────────────────────────────────────────────

async def _bot_can_send_media(client: Client, chat_id: int) -> bool:
    try:
        me = await client.get_me()
        member = await client.get_chat_member(chat_id, me.id)
        if member.status.name == "ADMINISTRATOR":
            return getattr(member.privileges, "can_send_media_messages", True) is not False
        return True
    except Exception:
        return True


async def _is_group_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


def _vote_caption(initiator_name: str, count: int) -> str:
    bars = "🟢" * count + "⬜" * (VOTES_REQUIRED - count)
    return (
        f"🗳️ <b>𝗩𝗢𝗧𝗘 𝗧𝗢 𝗦𝗧𝗔𝗥𝗧</b>\n"
        f"──┈┄┄╌╌╌╌┄┄┈──\n\n"
        f"👤 <b>{initiator_name}</b> wants to start a match!\n\n"
        f"🏏 {bars}\n"
        f"<b>{count} / {VOTES_REQUIRED}</b> votes collected\n\n"
        f"⏳ <i>Voting closes in 2 minutes.</i>\n"
        f"Tap below to vote! 👇"
    )


def _vote_buttons(chat_id: int, count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"✅ Vote to Start  ({count}/{VOTES_REQUIRED})",
            callback_data=f"vote_start:{chat_id}",
        )],
        [InlineKeyboardButton("✖ Cancel", callback_data=f"vote_cancel:{chat_id}")],
    ])


async def _send_mode_picker(client: Client, message) -> None:
    chat_id = message.chat.id

    if await is_game_active(chat_id):
        await message.reply_text(
            "⚠️ <b>Game already running</b>\nFinish the current match first 🏏",
            parse_mode=ParseMode.HTML,
        )
        return

    if await _bot_can_send_media(client, chat_id):
        try:
            await message.reply_photo(
                photo=START_IMAGE_GROUP,
                caption=PICKER_CAPTION,
                parse_mode=ParseMode.HTML,
                reply_markup=_mode_buttons(),
            )
            return
        except Exception:
            pass

    await message.reply_text(
        PICKER_CAPTION,
        parse_mode=ParseMode.HTML,
        reply_markup=_mode_buttons(),
    )


async def _expire_vote(client: Client, chat_id: int) -> None:
    """Called after VOTE_TIMEOUT seconds if 3 votes were never reached."""
    await asyncio.sleep(VOTE_TIMEOUT)
    state = VOTE_STATE.pop(chat_id, None)
    if not state:
        return
    try:
        await state["message"].delete()
    except Exception:
        pass
    try:
        await client.send_message(
            chat_id,
            "⏰ <b>Voting expired.</b>\nNot enough votes to start the match.",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


async def _start_vote(client: Client, message) -> None:
    """Post the voting dialogue and register the expiry task."""
    chat_id = message.chat.id
    user = message.from_user
    initiator_name = user.first_name or "Captain"

    # Only one active vote per group
    if chat_id in VOTE_STATE:
        await message.reply_text(
            "🗳️ <b>A vote is already in progress!</b>\nTap the Vote button above.",
            parse_mode=ParseMode.HTML,
        )
        return

    if await is_game_active(chat_id):
        await message.reply_text(
            "⚠️ <b>Game already running</b>\nFinish the current match first 🏏",
            parse_mode=ParseMode.HTML,
        )
        return

    caption = _vote_caption(initiator_name, 0)
    buttons = _vote_buttons(chat_id, 0)

    try:
        vote_msg = await message.reply_photo(
            photo=VOTE_IMAGE,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=buttons,
        )
    except Exception:
        vote_msg = await message.reply_text(
            caption,
            parse_mode=ParseMode.HTML,
            reply_markup=buttons,
        )

    task = asyncio.create_task(_expire_vote(client, chat_id))

    VOTE_STATE[chat_id] = {
        "initiator_id": user.id,
        "initiator_name": initiator_name,
        "voters": set(),
        "message": vote_msg,
        "task": task,
        "client": client,
    }


# ── /start /play /newgame in groups ──────────────────────────────────────────

@Client.on_message(filters.command("start") & filters.group)
async def start_in_group(client: Client, message):
    if await _is_group_admin(client, message.chat.id, message.from_user.id):
        await _send_mode_picker(client, message)
    else:
        await _start_vote(client, message)


@Client.on_message(filters.command(["play", "newgame"]) & filters.group)
async def play_cmd(client: Client, message):
    if await _is_group_admin(client, message.chat.id, message.from_user.id):
        await _send_mode_picker(client, message)
    else:
        await _start_vote(client, message)


# ── vote callback ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^vote_start:(-?\d+)$"))
async def handle_vote(client, query):
    chat_id = int(query.matches[0].group(1))
    user_id = query.from_user.id
    user_name = query.from_user.first_name or "Someone"

    state = VOTE_STATE.get(chat_id)
    if not state:
        return await query.answer("⏰ This vote has already ended.", show_alert=True)

    if user_id in state["voters"]:
        return await query.answer("✅ You already voted!", show_alert=True)

    state["voters"].add(user_id)
    count = len(state["voters"])

    await query.answer(f"✅ Vote counted! ({count}/{VOTES_REQUIRED})")

    if count >= VOTES_REQUIRED:
        # Cancel expiry task
        state["task"].cancel()
        VOTE_STATE.pop(chat_id, None)

        # Delete vote message
        try:
            await query.message.delete()
        except Exception:
            pass

        # Show mode picker using a fake message context
        try:
            await client.send_photo(
                chat_id=chat_id,
                photo=START_IMAGE_GROUP,
                caption=PICKER_CAPTION,
                parse_mode=ParseMode.HTML,
                reply_markup=_mode_buttons(),
            )
        except Exception:
            await client.send_message(
                chat_id=chat_id,
                text=PICKER_CAPTION,
                parse_mode=ParseMode.HTML,
                reply_markup=_mode_buttons(),
            )
        return

    # Update the vote count on the message
    caption = _vote_caption(state["initiator_name"], count)
    buttons = _vote_buttons(chat_id, count)
    try:
        await query.message.edit_caption(
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=buttons,
        )
    except Exception:
        try:
            await query.message.edit_text(
                caption,
                parse_mode=ParseMode.HTML,
                reply_markup=buttons,
            )
        except Exception:
            pass


@Client.on_callback_query(filters.regex(r"^vote_cancel:(-?\d+)$"))
async def handle_vote_cancel(client, query):
    chat_id = int(query.matches[0].group(1))
    state = VOTE_STATE.get(chat_id)

    # Only the initiator or an admin can cancel
    user_id = query.from_user.id
    is_initiator = state and state["initiator_id"] == user_id
    is_admin = await _is_group_admin(client, chat_id, user_id)

    if not (is_initiator or is_admin):
        return await query.answer("Only the starter or an admin can cancel.", show_alert=True)

    if state:
        state["task"].cancel()
        VOTE_STATE.pop(chat_id, None)

    try:
        await query.message.delete()
    except Exception:
        try:
            await query.message.edit_text("✖ Vote cancelled.")
        except Exception:
            pass
    await query.answer("Vote cancelled.")


# ── mode picker callbacks ─────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^mode_cancel$"))
async def cancel_start(client, query):
    try:
        await query.message.delete()
    except Exception:
        try:
            await query.message.edit_text("✖ Cancelled.")
        except Exception:
            pass
    await query.answer("Cancelled")


@Client.on_callback_query(filters.regex("^mode_back$"))
async def back_to_start(client, query):
    await query.answer()
    try:
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=START_IMAGE_GROUP,
                caption=PICKER_CAPTION,
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=_mode_buttons(),
        )
    except MessageNotModified:
        pass
    except Exception:
        try:
            await query.message.edit_text(
                PICKER_CAPTION,
                parse_mode=ParseMode.HTML,
                reply_markup=_mode_buttons(),
            )
        except Exception:
            pass
