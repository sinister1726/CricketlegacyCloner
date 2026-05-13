"""
/editstats — Owner-only command to SET stats to an exact value (overrides, not adds).

Usage:
  /editstats @username <field> <value>   — set field to exact value
  /editstats fields                      — list all supported fields
"""

import html
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import Config
from database.connection import db

import time

OWNER_FILTER = filters.user(list(Config.OWNER_IDS))

# Re-use shared helpers from addstats
from plugins.admin.addstats import (
    NUMERIC_FIELDS, ALIASES, _resolve_field, _fields_text,
    _parse_num, _get_existing, _pending_key, _clean_pending,
    _PENDING as _ADDSTATS_PENDING,
)

# Separate pending store for editstats
_PENDING_ES: dict = {}
_TTL = 120


def _es_key(user_id: int) -> str:
    return f"es_{user_id}"


async def _apply_edit(user_id: int, edits: dict) -> dict:
    """SET fields to exact values (no incrementing)."""
    await db.ensure_pool()
    col     = db.db["user_stats"]
    existing = await col.find_one({"user_id": user_id}) or {}
    changes  = {}
    set_ops  = {}

    for field, value in edits.items():
        if field not in NUMERIC_FIELDS:
            continue
        old_val     = existing.get(field, 0)
        set_ops[field] = value
        changes[field]  = (old_val, value)

    if set_ops:
        await col.update_one(
            {"user_id": user_id},
            {"$set": set_ops},
            upsert=True,
        )
    return changes


def _preview_edit(target_user, existing: dict, edits: dict) -> str:
    name = html.escape(target_user.first_name)
    uid  = target_user.id
    lines = [
        f"📝 <b>Confirm Stats Edit (SET)</b>",
        f"👤 <a href='tg://user?id={uid}'>{name}</a>",
        "━━━━━━━━━━━━━━━━",
        "<b>Field</b>  |  <b>Current → Will be set to</b>",
    ]
    for field, value in edits.items():
        info = NUMERIC_FIELDS.get(field)
        if info is None:
            continue
        label, _ = info
        old = existing.get(field, 0)
        diff = value - old
        diff_str = f"(+{diff})" if diff > 0 else f"({diff})" if diff < 0 else "(no change)"
        lines.append(f"• {label}: <code>{old}</code> → <code>{value}</code> {diff_str}")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("⚠️ This will <b>overwrite</b> the current value. Confirm?")
    return "\n".join(lines)


def _result_edit(target_user, changes: dict) -> str:
    name = html.escape(target_user.first_name)
    uid  = target_user.id
    if not changes:
        return f"⚠️ No stats were changed for <a href='tg://user?id={uid}'>{name}</a>."
    lines = [
        f"✅ <b>Stats Set</b> — <a href='tg://user?id={uid}'>{name}</a>",
        "━━━━━━━━━━━━━━━━",
    ]
    for field, (old, new) in changes.items():
        label = NUMERIC_FIELDS.get(field, (field, False))[0]
        diff  = new - old
        diff_str = f"+{diff}" if diff >= 0 else str(diff)
        lines.append(f"• {label}: <code>{old}</code> → <code>{new}</code>  (<b>{diff_str}</b>)")
    lines.append("━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def _confirm_kb(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, Set",  callback_data=f"es_confirm:{key}"),
            InlineKeyboardButton("❌ Cancel",    callback_data=f"es_cancel:{key}"),
        ]
    ])


@Client.on_message(
    filters.command("editstats") & OWNER_FILTER & (filters.private | filters.group)
)
async def editstats_cmd(client: Client, message: Message):
    args = message.command[1:]

    if args and args[0].lower() == "fields":
        return await message.reply_text(
            _fields_text(), parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    if len(args) < 3:
        return await message.reply_text(
            "📝 <b>/editstats — Set exact stat values</b>\n\n"
            "<b>Usage:</b> <code>/editstats @username &lt;field&gt; &lt;value&gt;</code>\n"
            "<b>Fields:</b> <code>/editstats fields</code>\n\n"
            "<i>Unlike /addstats, this replaces the value instead of adding to it.</i>",
            parse_mode=ParseMode.HTML,
        )

    raw_user = args[0].lstrip("@")
    try:
        target = await client.get_users(int(raw_user) if raw_user.isdigit() else raw_user)
    except Exception:
        return await message.reply_text(
            f"❌ Could not find user <code>{html.escape(args[0])}</code>.",
            parse_mode=ParseMode.HTML,
        )

    field = _resolve_field(args[1])
    if field is None:
        return await message.reply_text(
            f"❌ Unknown field <code>{html.escape(args[1])}</code>.\n"
            "Send <code>/editstats fields</code> to see all field names.",
            parse_mode=ParseMode.HTML,
        )

    try:
        value = _parse_num(args[2])
        if value < 0:
            raise ValueError("negative")
    except (ValueError, AttributeError):
        return await message.reply_text(
            f"❌ Value must be a whole number ≥ 0, got <code>{html.escape(args[2])}</code>.\n"
            "Commas are fine — e.g. <code>2,534</code>.",
            parse_mode=ParseMode.HTML,
        )

    existing = await _get_existing(target.id)
    edits    = {field: value}

    # Clean stale
    now = time.time()
    for k in list(_PENDING_ES.keys()):
        if now - _PENDING_ES[k]["ts"] > _TTL:
            del _PENDING_ES[k]

    key = _es_key(message.from_user.id)
    _PENDING_ES[key] = {
        "target_id":   target.id,
        "target_name": target.first_name,
        "edits":       edits,
        "ts":          time.time(),
    }

    return await message.reply_text(
        _preview_edit(target, existing, edits),
        parse_mode=ParseMode.HTML,
        reply_markup=_confirm_kb(key),
    )


@Client.on_callback_query(filters.regex(r"^es_confirm:") & OWNER_FILTER)
async def es_confirm_cb(client: Client, cb: CallbackQuery):
    key     = cb.data.split(":", 1)[1]
    pending = _PENDING_ES.get(key)
    if not pending:
        return await cb.answer("⏰ Confirmation expired. Send the command again.", show_alert=True)

    await cb.answer("Applying…")
    del _PENDING_ES[key]

    try:
        target = await client.get_users(pending["target_id"])
    except Exception:
        return await cb.message.edit_text("❌ Could not fetch target user. Aborted.")

    changes = await _apply_edit(pending["target_id"], pending["edits"])
    await cb.message.edit_text(
        _result_edit(target, changes),
        parse_mode=ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r"^es_cancel:") & OWNER_FILTER)
async def es_cancel_cb(client: Client, cb: CallbackQuery):
    key = cb.data.split(":", 1)[1]
    _PENDING_ES.pop(key, None)
    await cb.answer("Cancelled.")
    try:
        await cb.message.edit_text("❌ <b>Edit cancelled.</b>", parse_mode=ParseMode.HTML)
    except Exception:
        pass
