import html
import time
import asyncio
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, PeerIdInvalid

from config import Config
from database.connection import db

OWNER_FILTER = filters.user(list(Config.OWNER_IDS))

# Pending state: owner is being asked for a group link
# {user_id: {"name": ..., "deadline": ..., "waiting": True}}
_pending_event_creation: dict = {}


# ─── helpers ─────────────────────────────────────────────────────────────────

def _events_col():
    return db.db["events"]


def _regs_col():
    return db.db["event_registrations"]


async def _get_active_event():
    return await _events_col().find_one({"active": True}, sort=[("created_at", -1)])


def _parse_deadline(raw: str):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            pass
    return None


def _fmt_deadline(dt: datetime) -> str:
    return dt.strftime("%d %b %Y")


def _event_list_buttons(events: list) -> InlineKeyboardMarkup:
    rows = []
    for ev in events:
        label = f"{'🟢' if ev.get('active') else '🔴'} {ev['name']} — {_fmt_deadline(ev['deadline'])}"
        rows.append([InlineKeyboardButton(label, callback_data=f"ev_detail:{str(ev['_id'])}")])
    rows.append([InlineKeyboardButton("❌ Close", callback_data="ev_close")])
    return InlineKeyboardMarkup(rows)


# ─── /start_event ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("start_event") & OWNER_FILTER)
async def start_event_cmd(client, message):
    args = message.command
    if len(args) < 3:
        return await message.reply_text(
            "⚠️ <b>Usage:</b> <code>/start_event [Event Name] [Deadline: YYYY-MM-DD]</code>\n\n"
            "<b>Example:</b> <code>/start_event Summer T20 League 2026-04-30</code>",
            parse_mode=ParseMode.HTML,
        )

    # Last arg = deadline, everything in between = name
    raw_deadline = args[-1]
    name = " ".join(args[1:-1]).strip()

    if not name:
        return await message.reply_text("❌ Event name cannot be empty.", parse_mode=ParseMode.HTML)

    deadline = _parse_deadline(raw_deadline)
    if not deadline:
        return await message.reply_text(
            "❌ Invalid date. Use <code>YYYY-MM-DD</code> or <code>DD-MM-YYYY</code>.",
            parse_mode=ParseMode.HTML,
        )

    _pending_event_creation[message.from_user.id] = {
        "name": name,
        "deadline": deadline,
    }

    await message.reply_text(
        f"🏆 <b>Creating Event:</b> <b>{html.escape(name)}</b>\n"
        f"📅 <b>Deadline:</b> {_fmt_deadline(deadline)}\n\n"
        "📎 Now send me the <b>group link or @username</b> of the required group "
        "(players must be a member of this group to register).\n\n"
        "<i>Send <code>cancel</code> to abort.</i>",
        parse_mode=ParseMode.HTML,
    )


# ─── Catch the group link reply ───────────────────────────────────────────────

@Client.on_message(filters.private & OWNER_FILTER & ~filters.command([]))
async def catch_event_group_link(client, message):
    uid = message.from_user.id
    pending = _pending_event_creation.get(uid)
    if not pending:
        return

    text = (message.text or "").strip()
    if text.lower() == "cancel":
        _pending_event_creation.pop(uid, None)
        return await message.reply_text("❌ Event creation cancelled.")

    # Parse link / username
    group_ref = text
    if "t.me/" in group_ref:
        part = group_ref.split("t.me/")[-1].strip("/").split("/")[0]
        group_ref = f"@{part}" if not part.startswith("+") else group_ref

    wait = await message.reply_text("🔍 Verifying group…")

    try:
        chat = await client.get_chat(group_ref)
        group_id = chat.id
        group_title = chat.title or group_ref
        invite_link = text if "t.me/" in text else (chat.invite_link or text)
    except Exception as e:
        await wait.edit_text(
            f"❌ Could not resolve group: <code>{html.escape(str(e))}</code>\n"
            "Make sure the bot is in that group and try again.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Deactivate any existing active event
    await _events_col().update_many({"active": True}, {"$set": {"active": False}})

    event_doc = {
        "name": pending["name"],
        "deadline": pending["deadline"],
        "group_id": group_id,
        "group_title": group_title,
        "group_link": invite_link,
        "created_by": uid,
        "created_at": time.time(),
        "active": True,
    }
    result = await _events_col().insert_one(event_doc)
    _pending_event_creation.pop(uid, None)

    await wait.edit_text(
        "✅ <b>Event Created Successfully!</b>\n\n"
        f"🏆 <b>{html.escape(pending['name'])}</b>\n"
        f"📅 <b>Deadline:</b> {_fmt_deadline(pending['deadline'])}\n"
        f"👥 <b>Required Group:</b> {html.escape(group_title)}\n"
        f"🆔 <b>Event ID:</b> <code>{result.inserted_id}</code>\n\n"
        "Players can now use /register to join!",
        parse_mode=ParseMode.HTML,
    )


# ─── /register ────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("register"))
async def register_cmd(client, message):
    event = await _get_active_event()
    if not event:
        return await message.reply_text(
            "😴 <b>No active event right now.</b>\nCheck back later!",
            parse_mode=ParseMode.HTML,
        )

    deadline = event["deadline"]
    if isinstance(deadline, datetime) and datetime.utcnow() > deadline:
        return await message.reply_text(
            f"⏰ <b>Registration is closed!</b>\n"
            f"The deadline was {_fmt_deadline(deadline)}.",
            parse_mode=ParseMode.HTML,
        )

    user = message.from_user
    group_id = event.get("group_id")
    group_title = event.get("group_title", "the required group")
    group_link = event.get("group_link", "")

    # Check membership
    try:
        member = await client.get_chat_member(group_id, user.id)
        if member.status.value in ("left", "banned", "kicked"):
            raise UserNotParticipant
    except (UserNotParticipant, Exception):
        link_btn = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"👥 Join {group_title}", url=group_link)
        ]]) if group_link else None
        return await message.reply_text(
            f"🔒 <b>You must join the event group first!</b>\n\n"
            f"📌 Group: <b>{html.escape(group_title)}</b>\n"
            f"After joining, come back and send /register again.",
            parse_mode=ParseMode.HTML,
            reply_markup=link_btn,
        )

    event_id = str(event["_id"])

    existing = await _regs_col().find_one({"event_id": event_id, "user_id": user.id})
    if existing:
        return await message.reply_text(
            f"✅ <b>You're already registered</b> for <b>{html.escape(event['name'])}</b>!\n"
            "Use /deregister to withdraw.",
            parse_mode=ParseMode.HTML,
        )

    username = user.username or None
    first_name = user.first_name or "Player"

    await _regs_col().insert_one({
        "event_id": event_id,
        "user_id": user.id,
        "username": username,
        "first_name": first_name,
        "registered_at": time.time(),
    })

    count = await _regs_col().count_documents({"event_id": event_id})

    await message.reply_text(
        f"🎉 <b>Registered successfully!</b>\n\n"
        f"🏆 <b>Event:</b> {html.escape(event['name'])}\n"
        f"📅 <b>Deadline:</b> {_fmt_deadline(deadline)}\n"
        f"👥 <b>Total Registrations:</b> {count}\n\n"
        "Good luck! 🏏",
        parse_mode=ParseMode.HTML,
    )


# ─── /deregister ──────────────────────────────────────────────────────────────

@Client.on_message(filters.command("deregister"))
async def deregister_cmd(client, message):
    event = await _get_active_event()
    if not event:
        return await message.reply_text("😴 No active event to deregister from.", parse_mode=ParseMode.HTML)

    user = message.from_user
    event_id = str(event["_id"])

    result = await _regs_col().delete_one({"event_id": event_id, "user_id": user.id})
    if result.deleted_count == 0:
        return await message.reply_text(
            f"❌ You are not registered for <b>{html.escape(event['name'])}</b>.",
            parse_mode=ParseMode.HTML,
        )

    await message.reply_text(
        f"👋 <b>Deregistered</b> from <b>{html.escape(event['name'])}</b>.\n"
        "You can re-register anytime before the deadline with /register.",
        parse_mode=ParseMode.HTML,
    )


# ─── /list_events ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command(["list_events", "events"]))
async def list_events_cmd(client, message):
    cursor = _events_col().find({}).sort("created_at", -1).limit(10)
    events = await cursor.to_list(10)

    if not events:
        return await message.reply_text("📋 No events found yet.", parse_mode=ParseMode.HTML)

    active = next((e for e in events if e.get("active")), None)
    if active:
        count = await _regs_col().count_documents({"event_id": str(active["_id"])})
        header = (
            "🟢 <b>ACTIVE EVENT</b>\n"
            f"🏆 <b>{html.escape(active['name'])}</b>\n"
            f"📅 Deadline: <b>{_fmt_deadline(active['deadline'])}</b>\n"
            f"👥 Group: <b>{html.escape(active.get('group_title', '—'))}</b>\n"
            f"✅ Registered: <b>{count}</b>\n\n"
        )
    else:
        header = "📋 <b>No active event.</b>\n\n"

    header += "📜 <b>All Events:</b>"
    await message.reply_text(
        header,
        parse_mode=ParseMode.HTML,
        reply_markup=_event_list_buttons(events),
    )


# ─── /event_players — owner sees all registered players ───────────────────────

@Client.on_message(filters.command("event_players") & OWNER_FILTER)
async def event_players_cmd(client, message):
    event = await _get_active_event()
    if not event:
        return await message.reply_text("😴 No active event.", parse_mode=ParseMode.HTML)

    event_id = str(event["_id"])
    cursor = _regs_col().find({"event_id": event_id}).sort("registered_at", 1)
    players = await cursor.to_list(500)

    if not players:
        return await message.reply_text(
            f"📋 <b>{html.escape(event['name'])}</b>\n\nNo registrations yet.",
            parse_mode=ParseMode.HTML,
        )

    lines = []
    for i, p in enumerate(players, 1):
        name = html.escape(p.get("first_name") or "Player")
        uname = f" (@{p['username']})" if p.get("username") else ""
        lines.append(f"{i}. <a href='tg://user?id={p['user_id']}'>{name}</a>{uname}")

    chunk_size = 30
    for chunk_start in range(0, len(lines), chunk_size):
        chunk = lines[chunk_start:chunk_start + chunk_size]
        header = (
            f"📋 <b>{html.escape(event['name'])}</b> — Registrations ({len(players)} total)\n"
            "─────────────────────\n"
        ) if chunk_start == 0 else ""
        await message.reply_text(
            header + "\n".join(chunk),
            parse_mode=ParseMode.HTML,
        )


# ─── /end_event — owner force-closes an event ─────────────────────────────────

@Client.on_message(filters.command("end_event") & OWNER_FILTER)
async def end_event_cmd(client, message):
    event = await _get_active_event()
    if not event:
        return await message.reply_text("😴 No active event to end.", parse_mode=ParseMode.HTML)

    confirm_btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ End Event", callback_data=f"ev_end:{event['_id']}"),
        InlineKeyboardButton("❌ Cancel", callback_data="ev_close"),
    ]])
    count = await _regs_col().count_documents({"event_id": str(event["_id"])})
    await message.reply_text(
        f"⚠️ <b>End this event?</b>\n\n"
        f"🏆 <b>{html.escape(event['name'])}</b>\n"
        f"✅ Registered: <b>{count} players</b>\n\n"
        "This will close registration permanently.",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_btn,
    )


# ─── Callbacks ────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^ev_detail:(.+)$"))
async def ev_detail_cb(client, query):
    from bson import ObjectId
    oid = query.matches[0].group(1)
    try:
        event = await _events_col().find_one({"_id": ObjectId(oid)})
    except Exception:
        return await query.answer("Event not found.", show_alert=True)

    if not event:
        return await query.answer("Event not found.", show_alert=True)

    count = await _regs_col().count_documents({"event_id": str(event["_id"])})
    status = "🟢 Active" if event.get("active") else "🔴 Ended"
    text = (
        f"{status} — <b>{html.escape(event['name'])}</b>\n"
        f"📅 Deadline: <b>{_fmt_deadline(event['deadline'])}</b>\n"
        f"👥 Group: <b>{html.escape(event.get('group_title', '—'))}</b>\n"
        f"✅ Registered: <b>{count} players</b>\n"
    )
    back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="ev_back")]])
    try:
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_btn)
    except Exception:
        pass
    await query.answer()


@Client.on_callback_query(filters.regex(r"^ev_end:(.+)$") & OWNER_FILTER)
async def ev_end_cb(client, query):
    from bson import ObjectId
    oid = query.matches[0].group(1)
    try:
        await _events_col().update_one({"_id": ObjectId(oid)}, {"$set": {"active": False}})
    except Exception as e:
        return await query.answer(f"Error: {e}", show_alert=True)
    await query.message.edit_text("🔴 <b>Event ended.</b> Registration is now closed.", parse_mode=ParseMode.HTML)
    await query.answer("Event ended.")


@Client.on_callback_query(filters.regex(r"^ev_close$"))
async def ev_close_cb(client, query):
    try:
        await query.message.delete()
    except Exception:
        pass
    await query.answer()


@Client.on_callback_query(filters.regex(r"^ev_back$"))
async def ev_back_cb(client, query):
    cursor = _events_col().find({}).sort("created_at", -1).limit(10)
    events = await cursor.to_list(10)
    if not events:
        await query.message.edit_text("📋 No events found.", parse_mode=ParseMode.HTML)
        return await query.answer()

    active = next((e for e in events if e.get("active")), None)
    header = ""
    if active:
        count = await _regs_col().count_documents({"event_id": str(active["_id"])})
        header = (
            "🟢 <b>ACTIVE EVENT</b>\n"
            f"🏆 <b>{html.escape(active['name'])}</b>\n"
            f"📅 Deadline: <b>{_fmt_deadline(active['deadline'])}</b>\n"
            f"✅ Registered: <b>{count}</b>\n\n"
        )
    header += "📜 <b>All Events:</b>"
    try:
        await query.message.edit_text(
            header,
            parse_mode=ParseMode.HTML,
            reply_markup=_event_list_buttons(events),
        )
    except Exception:
        pass
    await query.answer()
