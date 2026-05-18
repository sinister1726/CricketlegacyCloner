import html
import time
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, PeerIdInvalid

from config import Config
from database.connection import db

OWNER_FILTER = filters.user(list(Config.OWNER_IDS))

_pending: dict = {}      # event creation wizard  {user_id: state_dict}
_pending_reg: dict = {}  # registration flow       {user_id: state_dict}


# ─── DB helpers ───────────────────────────────────────────────────────────────

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


# ─── Wizard markup helpers ────────────────────────────────────────────────────

def _markup_reg_type():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("♾ No Limit",   callback_data="evw_type_nolimit"),
            InlineKeyboardButton("🔢 Set Limit",  callback_data="evw_type_limit"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="evw_cancel")],
    ])

def _markup_baseprice():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❌ No Base Price", callback_data="evw_bp_no"),
            InlineKeyboardButton("💰 Set Prices",    callback_data="evw_bp_yes"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="evw_cancel")],
    ])

def _markup_teams():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❌ No Teams",   callback_data="evw_teams_no"),
            InlineKeyboardButton("👥 Add Teams",  callback_data="evw_teams_yes"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="evw_cancel")],
    ])


# ─── /start_event ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("start_event") & OWNER_FILTER)
async def start_event_cmd(client, message):
    uid = message.from_user.id
    _pending[uid] = {"step": "await_name"}
    await message.reply_text(
        "🏆 <b>Create New Event — Step 1/6</b>\n\n"
        "What is the <b>name</b> of this event?\n\n"
        "<i>Send <code>cancel</code> at any time to abort.</i>",
        parse_mode=ParseMode.HTML,
    )


# ─── Wizard text handler ───────────────────────────────────────────────────────

@Client.on_message(filters.private & OWNER_FILTER & ~filters.command([]))
async def wizard_text_handler(client, message):
    uid   = message.from_user.id
    state = _pending.get(uid)
    if not state:
        return

    text = (message.text or "").strip()
    if text.lower() == "cancel":
        _pending.pop(uid, None)
        return await message.reply_text("❌ Event creation cancelled.")

    step = state["step"]

    # ── Step 1: Name ──────────────────────────────────────────────────────────
    if step == "await_name":
        if not text:
            return await message.reply_text("❌ Name can't be empty. Try again.")
        state["name"] = text
        state["step"] = "await_type"
        await message.reply_text(
            f"✅ <b>Name:</b> {html.escape(text)}\n\n"
            "📊 <b>Step 2/6 — Registration Limit</b>\n"
            "Is there a cap on how many players can register?",
            parse_mode=ParseMode.HTML,
            reply_markup=_markup_reg_type(),
        )

    # ── Step 2b: Limit number (after button chose limit) ─────────────────────
    elif step == "await_limit_num":
        if not text.isdigit() or int(text) < 1:
            return await message.reply_text(
                "❌ Send a valid number, e.g. <code>32</code>.", parse_mode=ParseMode.HTML
            )
        state["reg_limit"] = int(text)
        state["step"] = "await_baseprice"
        await message.reply_text(
            f"✅ <b>Limit:</b> {text} players max.\n\n"
            "💰 <b>Step 3/6 — Base Price</b>\n"
            "Should players pick a base price when registering?",
            parse_mode=ParseMode.HTML,
            reply_markup=_markup_baseprice(),
        )

    # ── Step 3b: Prices text input ────────────────────────────────────────────
    elif step == "await_prices_input":
        prices = [int(p.strip()) for p in text.split(",") if p.strip().isdigit()]
        if not prices:
            return await message.reply_text(
                "❌ Invalid format. Send comma-separated numbers.\n"
                "<b>Example:</b> <code>100,150,200</code>",
                parse_mode=ParseMode.HTML,
            )
        state["base_prices"] = prices
        state["step"] = "await_teams"
        price_str = "  ·  ".join(f"₹{p}" for p in prices)
        await message.reply_text(
            f"✅ <b>Base Prices:</b> {price_str}\n\n"
            "👥 <b>Step 4/6 — Teams</b>\n"
            "Are there teams players can choose when registering?\n"
            "<i>(e.g. Girls, Boys)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=_markup_teams(),
        )

    # ── Step 4b: Team names text input ────────────────────────────────────────
    elif step == "await_teamnames_input":
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if len(parts) < 2:
            return await message.reply_text(
                "❌ Send at least 2 team names separated by commas.\n"
                "<b>Example:</b> <code>Girls,Boys</code>",
                parse_mode=ParseMode.HTML,
            )
        state["teams"] = parts
        state["step"] = "await_deadline"
        teams_str = "  ·  ".join(f"<b>{html.escape(t)}</b>" for t in parts)
        await message.reply_text(
            f"✅ <b>Teams:</b> {teams_str}\n\n"
            "📅 <b>Step 5/6 — Registration Deadline</b>\n"
            "Send the deadline date:\n"
            "<b>Format:</b> <code>DD-MM-YYYY</code> or <code>YYYY-MM-DD</code>",
            parse_mode=ParseMode.HTML,
        )

    # ── Step 5: Deadline ──────────────────────────────────────────────────────
    elif step == "await_deadline":
        dl = _parse_deadline(text)
        if not dl:
            return await message.reply_text(
                "❌ Invalid date format.\n"
                "Use <code>DD-MM-YYYY</code> or <code>YYYY-MM-DD</code>.",
                parse_mode=ParseMode.HTML,
            )
        state["deadline"] = dl
        state["step"] = "await_group"
        await message.reply_text(
            f"✅ <b>Deadline:</b> {_fmt_deadline(dl)}\n\n"
            "🔗 <b>Step 6/6 — Required Group</b>\n"
            "Send the <b>group @username or invite link</b>.\n"
            "Players must be a member of this group to register.\n"
            "<i>(The bot must already be in that group)</i>",
            parse_mode=ParseMode.HTML,
        )

    # ── Step 6: Group link → create event ────────────────────────────────────
    elif step == "await_group":
        group_ref = text
        if "t.me/" in group_ref:
            part      = group_ref.split("t.me/")[-1].strip("/").split("/")[0]
            group_ref = f"@{part}" if not part.startswith("+") else group_ref

        wait = await message.reply_text("🔍 Verifying group…")
        try:
            chat        = await client.get_chat(group_ref)
            group_id    = chat.id
            group_title = chat.title or text
            invite_link = text if "t.me/" in text else (chat.invite_link or text)
        except Exception as e:
            return await wait.edit_text(
                f"❌ Could not resolve group: <code>{html.escape(str(e))}</code>\n"
                "Make sure the bot is inside that group and try again.",
                parse_mode=ParseMode.HTML,
            )

        await _events_col().update_many({"active": True}, {"$set": {"active": False}})

        event_doc = {
            "name":        state["name"],
            "deadline":    state["deadline"],
            "group_id":    group_id,
            "group_title": group_title,
            "group_link":  invite_link,
            "created_by":  uid,
            "created_at":  time.time(),
            "active":      True,
            "reg_limit":   state.get("reg_limit"),
            "base_prices": state.get("base_prices"),
            "teams":       state.get("teams"),
        }
        await _events_col().insert_one(event_doc)
        _pending.pop(uid, None)

        limit_line = f"{state['reg_limit']} players max" if state.get("reg_limit") else "No limit"
        price_line = "  ·  ".join(f"₹{p}" for p in state["base_prices"]) if state.get("base_prices") else "None"
        teams_line = "  ·  ".join(state["teams"]) if state.get("teams") else "None"

        await wait.edit_text(
            "✅ <b>Event Created!</b>\n\n"
            f"🏆 <b>{html.escape(state['name'])}</b>\n"
            f"📅 Deadline: <b>{_fmt_deadline(state['deadline'])}</b>\n"
            f"👥 Group: <b>{html.escape(group_title)}</b>\n"
            f"🔢 Limit: <b>{limit_line}</b>\n"
            f"💰 Base Prices: <b>{price_line}</b>\n"
            f"🏅 Teams: <b>{teams_line}</b>\n\n"
            "Players can now use /register to join! 🏏",
            parse_mode=ParseMode.HTML,
        )


# ─── Wizard button callbacks ───────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^evw_cancel$") & OWNER_FILTER)
async def evw_cancel_cb(client, query):
    _pending.pop(query.from_user.id, None)
    try:
        await query.message.edit_text("❌ Event creation cancelled.")
    except Exception:
        pass
    await query.answer("Cancelled.")


@Client.on_callback_query(filters.regex(r"^evw_type_(nolimit|limit)$") & OWNER_FILTER)
async def evw_type_cb(client, query):
    uid   = query.from_user.id
    state = _pending.get(uid)
    if not state or state.get("step") != "await_type":
        return await query.answer("This button has expired.", show_alert=True)

    choice = query.matches[0].group(1)
    if choice == "nolimit":
        state["reg_limit"] = None
        state["step"]      = "await_baseprice"
        await query.message.edit_text(
            "✅ <b>Limit:</b> No limit.\n\n"
            "💰 <b>Step 3/6 — Base Price</b>\n"
            "Should players pick a base price when registering?",
            parse_mode=ParseMode.HTML,
            reply_markup=_markup_baseprice(),
        )
    else:
        state["step"] = "await_limit_num"
        await query.message.edit_text(
            "📊 <b>Step 2/6 — Registration Limit</b>\n"
            "How many players can register? Send the number.\n"
            "<b>Example:</b> <code>32</code>",
            parse_mode=ParseMode.HTML,
        )
    await query.answer()


@Client.on_callback_query(filters.regex(r"^evw_bp_(yes|no)$") & OWNER_FILTER)
async def evw_bp_cb(client, query):
    uid   = query.from_user.id
    state = _pending.get(uid)
    if not state or state.get("step") != "await_baseprice":
        return await query.answer("This button has expired.", show_alert=True)

    choice = query.matches[0].group(1)
    if choice == "no":
        state["base_prices"] = None
        state["step"]        = "await_teams"
        await query.message.edit_text(
            "✅ <b>Base Price:</b> None.\n\n"
            "👥 <b>Step 4/6 — Teams</b>\n"
            "Are there teams players can choose from when registering?",
            parse_mode=ParseMode.HTML,
            reply_markup=_markup_teams(),
        )
    else:
        state["step"] = "await_prices_input"
        await query.message.edit_text(
            "💰 <b>Step 3/6 — Base Prices</b>\n"
            "Send the available prices as a comma-separated list.\n"
            "<b>Example:</b> <code>100,150,200</code>",
            parse_mode=ParseMode.HTML,
        )
    await query.answer()


@Client.on_callback_query(filters.regex(r"^evw_teams_(yes|no)$") & OWNER_FILTER)
async def evw_teams_cb(client, query):
    uid   = query.from_user.id
    state = _pending.get(uid)
    if not state or state.get("step") != "await_teams":
        return await query.answer("This button has expired.", show_alert=True)

    choice = query.matches[0].group(1)
    if choice == "no":
        state["teams"] = None
        state["step"]  = "await_deadline"
        await query.message.edit_text(
            "✅ <b>Teams:</b> None.\n\n"
            "📅 <b>Step 5/6 — Registration Deadline</b>\n"
            "Send the deadline date:\n"
            "<b>Format:</b> <code>DD-MM-YYYY</code> or <code>YYYY-MM-DD</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        state["step"] = "await_teamnames_input"
        await query.message.edit_text(
            "👥 <b>Step 4/6 — Teams</b>\n"
            "Send team names separated by commas.\n"
            "<b>Example:</b> <code>Girls,Boys</code>  or  <code>India,Pakistan,Sri Lanka</code>",
            parse_mode=ParseMode.HTML,
        )
    await query.answer()


# ─── Registration helper ──────────────────────────────────────────────────────

async def _do_register(client, responder, user, event, event_id, *, team=None, base_price=None):
    deadline = event["deadline"]
    await _regs_col().insert_one({
        "event_id":      event_id,
        "user_id":       user.id,
        "username":      user.username,
        "first_name":    user.first_name or "Player",
        "team":          team,
        "base_price":    base_price,
        "registered_at": time.time(),
    })
    count  = await _regs_col().count_documents({"event_id": event_id})
    extras = ""
    if team:       extras += f"\n👥 <b>Team:</b> {html.escape(team)}"
    if base_price: extras += f"\n💰 <b>Base Price:</b> ₹{base_price}"

    text = (
        f"🎉 <b>Registered!</b>\n\n"
        f"🏆 <b>{html.escape(event['name'])}</b>\n"
        f"📅 Deadline: <b>{_fmt_deadline(deadline)}</b>"
        f"{extras}\n"
        f"👥 Total registered: <b>{count}</b>\n\n"
        "Good luck! 🏏"
    )
    if hasattr(responder, "message"):
        try:
            await responder.message.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            pass
        await responder.answer("Registered! 🎉")
    else:
        await responder.reply_text(text, parse_mode=ParseMode.HTML)


# ─── /register ────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("register"))
async def register_cmd(client, message):
    from config import Config
    if Config.IS_CLONE:
        return await message.reply_text("🔒 <b>Events are disabled in clone bots.</b>", parse_mode=ParseMode.HTML)
    user = message.from_user
    if not user:
        return

    event = await _get_active_event()
    if not event:
        return await message.reply_text("😴 <b>No active event right now.</b>", parse_mode=ParseMode.HTML)

    deadline = event["deadline"]
    if isinstance(deadline, datetime) and datetime.utcnow() > deadline:
        return await message.reply_text(
            f"⏰ <b>Registration closed!</b> Deadline was {_fmt_deadline(deadline)}.",
            parse_mode=ParseMode.HTML,
        )

    event_id  = str(event["_id"])
    reg_limit = event.get("reg_limit")
    if reg_limit:
        count = await _regs_col().count_documents({"event_id": event_id})
        if count >= reg_limit:
            return await message.reply_text(
                f"🔒 <b>Registration full!</b> Max {reg_limit} players reached.",
                parse_mode=ParseMode.HTML,
            )

    group_id    = event.get("group_id")
    group_title = event.get("group_title", "the required group")
    group_link  = event.get("group_link", "")
    is_member   = None
    if group_id:
        try:
            member    = await client.get_chat_member(group_id, user.id)
            status    = getattr(member.status, "name", str(member.status)).upper()
            is_member = False if status in ("LEFT", "BANNED", "KICKED", "RESTRICTED") else True
        except UserNotParticipant:
            is_member = False
        except Exception:
            is_member = None

    if is_member is False:
        link_btn = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"👥 Join {group_title}", url=group_link)
        ]]) if group_link else None
        return await message.reply_text(
            f"🔒 <b>Join the event group first!</b>\n\n"
            f"📌 <b>{html.escape(group_title)}</b>\nThen send /register again.",
            parse_mode=ParseMode.HTML,
            reply_markup=link_btn,
        )

    if is_member is None and group_id:
        await message.reply_text(
            "ℹ️ <i>Couldn't verify your membership — proceeding anyway.\n"
            f"Make sure you've joined <b>{html.escape(group_title)}</b>.</i>",
            parse_mode=ParseMode.HTML,
        )

    existing = await _regs_col().find_one({"event_id": event_id, "user_id": user.id})
    if existing:
        return await message.reply_text(
            f"✅ Already registered for <b>{html.escape(event['name'])}</b>!\n"
            "Use /deregister to withdraw.",
            parse_mode=ParseMode.HTML,
        )

    teams       = event.get("teams")
    base_prices = event.get("base_prices")

    if teams or base_prices:
        _pending_reg[user.id] = {
            "event_id":    event_id,
            "team":        None,
            "base_price":  None,
        }
        if teams:
            rows = []
            for i in range(0, len(teams), 2):
                row = [
                    InlineKeyboardButton(teams[j], callback_data=f"evreg_team:{event_id}:{j}")
                    for j in range(i, min(i + 2, len(teams)))
                ]
                rows.append(row)
            rows.append([InlineKeyboardButton("❌ Cancel", callback_data="evreg_cancel")])
            return await message.reply_text(
                f"🏆 <b>{html.escape(event['name'])}</b>\n\n"
                "👥 <b>Choose your team:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(rows),
            )
        price_rows = [
            [InlineKeyboardButton(f"₹{p}", callback_data=f"evreg_price:{event_id}:{p}")]
            for p in base_prices
        ]
        price_rows.append([InlineKeyboardButton("❌ Cancel", callback_data="evreg_cancel")])
        return await message.reply_text(
            f"🏆 <b>{html.escape(event['name'])}</b>\n\n"
            "💰 <b>Choose your base price:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(price_rows),
        )

    await _do_register(client, message, user, event, event_id)


# ─── Registration callbacks ────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^evreg_team:([^:]+):(\d+)$"))
async def evreg_team_cb(client, query):
    from bson import ObjectId
    uid      = query.from_user.id
    event_id = query.matches[0].group(1)
    idx      = int(query.matches[0].group(2))

    event = await _events_col().find_one({"_id": ObjectId(event_id)})
    if not event:
        return await query.answer("Event not found.", show_alert=True)

    teams = event.get("teams", [])
    if idx >= len(teams):
        return await query.answer("Invalid selection.", show_alert=True)

    team = teams[idx]
    pr   = _pending_reg.get(uid, {})
    pr["team"] = team

    base_prices = event.get("base_prices")
    if base_prices:
        _pending_reg[uid] = pr
        price_rows = [
            [InlineKeyboardButton(f"₹{p}", callback_data=f"evreg_price:{event_id}:{p}")]
            for p in base_prices
        ]
        price_rows.append([InlineKeyboardButton("❌ Cancel", callback_data="evreg_cancel")])
        try:
            await query.message.edit_text(
                f"✅ <b>Team:</b> {html.escape(team)}\n\n"
                "💰 <b>Now choose your base price:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(price_rows),
            )
        except Exception:
            pass
        return await query.answer()

    _pending_reg.pop(uid, None)
    await _do_register(client, query, query.from_user, event, event_id, team=team)


@Client.on_callback_query(filters.regex(r"^evreg_price:([^:]+):(\d+)$"))
async def evreg_price_cb(client, query):
    from bson import ObjectId
    uid      = query.from_user.id
    event_id = query.matches[0].group(1)
    price    = int(query.matches[0].group(2))

    event = await _events_col().find_one({"_id": ObjectId(event_id)})
    if not event:
        return await query.answer("Event not found.", show_alert=True)

    pr   = _pending_reg.pop(uid, {})
    team = pr.get("team")
    await _do_register(client, query, query.from_user, event, event_id, team=team, base_price=price)


@Client.on_callback_query(filters.regex(r"^evreg_cancel$"))
async def evreg_cancel_cb(client, query):
    _pending_reg.pop(query.from_user.id, None)
    try:
        await query.message.edit_text("❌ Registration cancelled.")
    except Exception:
        pass
    await query.answer("Cancelled.")


# ─── /deregister ──────────────────────────────────────────────────────────────

@Client.on_message(filters.command("deregister"))
async def deregister_cmd(client, message):
    from config import Config
    if Config.IS_CLONE:
        return await message.reply_text("🔒 <b>Events are disabled in clone bots.</b>", parse_mode=ParseMode.HTML)
    event = await _get_active_event()
    if not event:
        return await message.reply_text("😴 No active event to deregister from.", parse_mode=ParseMode.HTML)

    user     = message.from_user
    event_id = str(event["_id"])
    result   = await _regs_col().delete_one({"event_id": event_id, "user_id": user.id})
    if result.deleted_count == 0:
        return await message.reply_text(
            f"❌ You are not registered for <b>{html.escape(event['name'])}</b>.",
            parse_mode=ParseMode.HTML,
        )
    await message.reply_text(
        f"👋 <b>Deregistered</b> from <b>{html.escape(event['name'])}</b>.\n"
        "You can re-register anytime before the deadline.",
        parse_mode=ParseMode.HTML,
    )


# ─── /list_events ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command(["list_events", "events"]))
async def list_events_cmd(client, message):
    from config import Config
    if Config.IS_CLONE:
        return await message.reply_text("🔒 <b>Events are disabled in clone bots.</b>", parse_mode=ParseMode.HTML)
    cursor = _events_col().find({}).sort("created_at", -1).limit(10)
    events = await cursor.to_list(10)
    if not events:
        return await message.reply_text("📋 No events found yet.", parse_mode=ParseMode.HTML)

    active = next((e for e in events if e.get("active")), None)
    header = ""
    if active:
        count      = await _regs_col().count_documents({"event_id": str(active["_id"])})
        reg_limit  = active.get("reg_limit")
        limit_str  = f"{count}/{reg_limit}" if reg_limit else str(count)
        prices_str = "  ·  ".join(f"₹{p}" for p in active["base_prices"]) if active.get("base_prices") else "—"
        teams_str  = "  ·  ".join(active["teams"]) if active.get("teams") else "—"
        header = (
            "🟢 <b>ACTIVE EVENT</b>\n"
            f"🏆 <b>{html.escape(active['name'])}</b>\n"
            f"📅 Deadline: <b>{_fmt_deadline(active['deadline'])}</b>\n"
            f"👥 Group: <b>{html.escape(active.get('group_title', '—'))}</b>\n"
            f"✅ Registered: <b>{limit_str}</b>\n"
            f"💰 Base Prices: <b>{prices_str}</b>\n"
            f"🏅 Teams: <b>{teams_str}</b>\n\n"
        )
    else:
        header = "📋 <b>No active event.</b>\n\n"

    header += "📜 <b>All Events:</b>"
    await message.reply_text(header, parse_mode=ParseMode.HTML, reply_markup=_event_list_buttons(events))


# ─── /event_players ───────────────────────────────────────────────────────────

@Client.on_message(filters.command("event_players") & OWNER_FILTER)
async def event_players_cmd(client, message):
    event = await _get_active_event()
    if not event:
        return await message.reply_text("😴 No active event.", parse_mode=ParseMode.HTML)

    event_id = str(event["_id"])
    cursor   = _regs_col().find({"event_id": event_id}).sort("registered_at", 1)
    players  = await cursor.to_list(500)
    if not players:
        return await message.reply_text(
            f"📋 <b>{html.escape(event['name'])}</b>\n\nNo registrations yet.",
            parse_mode=ParseMode.HTML,
        )

    lines = []
    for i, p in enumerate(players, 1):
        name      = html.escape(p.get("first_name") or "Player")
        uname     = f" (@{p['username']})" if p.get("username") else ""
        team_tag  = f" [{html.escape(p['team'])}]" if p.get("team") else ""
        price_tag = f" ₹{p['base_price']}" if p.get("base_price") else ""
        lines.append(
            f"{i}. <a href='tg://user?id={p['user_id']}'>{name}</a>{uname}{team_tag}{price_tag}"
        )

    chunk_size = 30
    for start in range(0, len(lines), chunk_size):
        chunk  = lines[start:start + chunk_size]
        header = (
            f"📋 <b>{html.escape(event['name'])}</b> — {len(players)} registered\n\n"
        ) if start == 0 else ""
        await message.reply_text(header + "\n".join(chunk), parse_mode=ParseMode.HTML)


# ─── /end_event ───────────────────────────────────────────────────────────────

@Client.on_message(filters.command("end_event") & OWNER_FILTER)
async def end_event_cmd(client, message):
    event = await _get_active_event()
    if not event:
        return await message.reply_text("😴 No active event to end.", parse_mode=ParseMode.HTML)

    count = await _regs_col().count_documents({"event_id": str(event["_id"])})
    btn   = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ End Event", callback_data=f"ev_end:{event['_id']}"),
        InlineKeyboardButton("❌ Cancel",    callback_data="ev_close"),
    ]])
    await message.reply_text(
        f"⚠️ <b>End this event?</b>\n\n"
        f"🏆 <b>{html.escape(event['name'])}</b>\n"
        f"✅ Registered: <b>{count} players</b>\n\n"
        "This will close registration permanently.",
        parse_mode=ParseMode.HTML,
        reply_markup=btn,
    )


# ─── Callbacks (detail / end / close / back) ──────────────────────────────────

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

    event_id   = str(event["_id"])
    count      = await _regs_col().count_documents({"event_id": event_id})
    reg_limit  = event.get("reg_limit")
    status     = "🟢 Active" if event.get("active") else "🔴 Ended"
    limit_str  = f"{count}/{reg_limit}" if reg_limit else str(count)
    prices_str = "  ·  ".join(f"₹{p}" for p in event["base_prices"]) if event.get("base_prices") else "None"
    teams_str  = "  ·  ".join(event["teams"]) if event.get("teams") else "None"

    text = (
        f"{status} — <b>{html.escape(event['name'])}</b>\n"
        f"📅 Deadline: <b>{_fmt_deadline(event['deadline'])}</b>\n"
        f"👥 Group: <b>{html.escape(event.get('group_title', '—'))}</b>\n"
        f"✅ Registered: <b>{limit_str}</b>\n"
        f"💰 Base Prices: <b>{prices_str}</b>\n"
        f"🏅 Teams: <b>{teams_str}</b>"
    )
    try:
        await query.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="ev_back")]]),
        )
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
        count  = await _regs_col().count_documents({"event_id": str(active["_id"])})
        header = (
            "🟢 <b>ACTIVE EVENT</b>\n"
            f"🏆 <b>{html.escape(active['name'])}</b>\n"
            f"📅 Deadline: <b>{_fmt_deadline(active['deadline'])}</b>\n"
            f"✅ Registered: <b>{count}</b>\n\n"
        )
    header += "📜 <b>All Events:</b>"
    try:
        await query.message.edit_text(header, parse_mode=ParseMode.HTML, reply_markup=_event_list_buttons(events))
    except Exception:
        pass
    await query.answer()
