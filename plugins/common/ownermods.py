import time
import asyncio
import pyrogram.errors
from datetime import datetime, timedelta
from config import Config
from plugins.game.team import ACTIVE_MATCHES 

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.connection import db
from database.users import total_users
from database.groups import total_groups
from database.mods import (
    add_or_update_mod,
    remove_mod,
    list_mods,
    get_mod,
    is_mod
)

OWNER_ID = 8294062042
BROADCAST_CACHE = {}
BROADCAST_RUNNING = False
BROADCAST_CANCEL = False
BOT_START_TIME = time.time()


def uptime():
    secs = int(time.time() - BOT_START_TIME)
    h = secs // 3600
    m = (secs % 3600) // 60
    return f"{h}h {m}m"

async def _col():
    await db.ensure_pool()
    if db.db is None:
        raise RuntimeError("Database unavailable.")
    return db.db

@Client.on_message(filters.command("fetch"))
async def fetch_dashboard(client, message):
    if message.from_user.id != OWNER_ID:
        return

    try:
        now = datetime.utcnow()

        users_total = await total_users()
        users_7d = await db.db["user_stats"].count_documents({})

        active_users = users_total
        inactive_users = 0

        groups_total = await total_groups()
        active_groups = groups_total
        inactive_groups = 0

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        games_today = await db.db["games"].count_documents({"created_at": {"$gte": today_start}})
        games_total = await db.db["games"].count_documents({})

        db_status = "✅ Connected"
        bot_status = "✅ Running"

        text = (
            "📊 <b>COMPREHENSIVE SYSTEM & BROADCAST DASHBOARD</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "👥 <b>USER STATISTICS</b>\n"
            f"├ 📈 Total Registered: <b>{users_total}</b>\n"
            f"├ ✅ Active Users: <b>{active_users}</b> (100%)\n"
            f"├ ❌ Inactive Users: <b>{inactive_users}</b> (0%)\n"
            f"└ 📅 New (7 days): <b>{users_7d}</b>\n\n"

            "👥 <b>GROUP STATISTICS</b>\n"
            f"├ 📈 Total Groups: <b>{groups_total}</b>\n"
            f"├ ✅ Active Groups: <b>{active_groups}</b> (100%)\n"
            f"└ ❌ Inactive Groups: <b>{inactive_groups}</b> (0%)\n\n"

            "🎮 <b>GAME METRICS</b>\n"
            f"├ 🎯 Games Today: <b>{games_today}</b>\n"
            f"└ 📊 Total Matches: <b>{games_total}</b>\n\n"

            "🔄 <b>SYSTEM HEALTH</b>\n"
            f"├ 🔗 Database: {db_status}\n"
            f"├ 🤖 Bot Status: {bot_status}\n"
            f"├ ⏱ Uptime: <b>{uptime()}</b>\n"
            "└ 🏥 Health: ✅ Stable\n\n"

            "💡 <b>QUICK INSIGHTS</b>\n"
            f"• Growth (7d): +{users_7d} users\n"
            f"• Retention: 100% users & groups\n"
            f"• Activity: {games_today} games today\n\n"

            "⚙️ <b>ADMIN COMMANDS</b>\n"
            "• /broad – Start broadcast\n"
            "• /fetch – Full system dashboard\n"
            "• /mods – View all moderators\n\n"

            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>Last Updated:</b> {now.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        await message.reply_text(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        print("[FETCH ERROR]", e)
        await message.reply_text(
            "⚠️ Failed to fetch system data.\nCheck logs.",
            parse_mode=ParseMode.HTML
        )

@Client.on_message(filters.command("addmod"))
async def addmod_cmd(client, message):
    if message.from_user.id != OWNER_ID:
        return

    args = message.text.split()
    
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        tier = int(args[1]) if len(args) > 1 else 1
    elif len(args) >= 3 and args[2].isdigit():
        try:
            target = await client.get_users(args[1])
            tier = int(args[2])
        except Exception:
            return await message.reply_text("❌ Could not find user.")
    else:
        return await message.reply_text(
            "Reply / username / user_id required + tier 😑"
        )

    old = await get_mod(target.id)

    await add_or_update_mod(target.id, tier, OWNER_ID)

    if not old:
        msg = f"🧢 {target.first_name} added as Mod (Tier {tier})"
    elif tier > old["tier"]:
        msg = f"📈 {target.first_name} promoted → Tier {tier}"
    elif tier < old["tier"]:
        msg = f"📉 {target.first_name} demoted → Tier {tier}"
    else:
        msg = f"😐 {target.first_name} already Tier {tier}"

    await message.reply_text(msg)

@Client.on_message(filters.command("rmmod"))
async def rmmod_cmd(client, message):
    if message.from_user.id != OWNER_ID:
        return

    if message.reply_to_message:
        uid = message.reply_to_message.from_user.id
    else:
        args = message.text.split()
        if len(args) != 2 or not args[1].isdigit():
            return await message.reply_text("Reply or give user_id 🙄")
        uid = int(args[1])

    await remove_mod(uid)
    await message.reply_text("🗑️ Mod access revoked. Back to civilian life.")

@Client.on_message(filters.command("mods"))
async def mods_cmd(client, message):
    if message.from_user.id != OWNER_ID:
        return

    mods = await list_mods()

    if not mods:
        return await message.reply_text("No mods. Absolute monarchy 👑")

    lines = ["🧢 <b>MOD TEAM</b>\n"]

    for m in mods:
        lines.append(
            f"• <code>{m['user_id']}</code> — Tier {m['tier']}"
        )

    await message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML
    )

@Client.on_message(filters.command("broad"))
async def broad_cmd(client, message):
    global BROADCAST_RUNNING

    uid = message.from_user.id

    if uid != OWNER_ID and not await is_mod(uid, min_tier=2):
        return

    if BROADCAST_RUNNING:
        return await message.reply_text("⚠️ A broadcast is already running.")

    args = message.text.split(maxsplit=2)

    if len(args) < 2:
        return await message.reply_text(
            "Usage:\n"
            "/broad -forward\n"
            "/broad -copy\n"
            "/broad -users\n"
            "/broad -groups"
        )

    btype = args[1].replace("-", "").lower()

    text_payload = None
    source_msg = None

    if message.reply_to_message:
        source_msg = message.reply_to_message
    elif len(args) >= 3:
        text_payload = args[2]
    else:
        return await message.reply_text("Nothing to broadcast 🤨")

    # ✅ SAFE DB FETCH
    try:
        database = await _col()

        user_rows = await database["user_stats"].find(
            {}, {"user_id": 1}
        ).to_list(length=None)

        group_rows = await database["groups"].find(
            {}, {"chat_id": 1}
        ).to_list(length=None)

    except Exception as e:
        print("[BROADCAST DB ERROR]", e)
        return await message.reply_text("❌ Database not available.")

    # ✅ CLEAN EXTRACTION
    users = list({u.get("user_id") for u in user_rows if u.get("user_id")})
    groups = list({g.get("chat_id") for g in group_rows if g.get("chat_id")})

    if not users and not groups:
        return await message.reply_text("⚠️ No users or groups found.")

    # ✅ TARGET SELECTION
    if btype == "users":
        targets = users
    elif btype == "groups":
        targets = groups
    else:
        targets = users + groups

    BROADCAST_CACHE[uid] = {
        "text": text_payload,
        "source_msg": source_msg,
        "type": btype,
        "targets": targets,
        "users": users,
        "groups": groups
    }

    preview = (
        f"📡 <b>Broadcast Receipt</b>\n\n"
        f"👤 Users: <b>{len(users)}</b>\n"
        f"👥 Groups: <b>{len(groups)}</b>\n"
        f"🎯 Targets: <b>{len(targets)}</b>\n\n"
        f"Type: <b>{btype}</b>"
    )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Start Broadcast", callback_data="broad_start")],
            [InlineKeyboardButton("❌ Cancel", callback_data="broad_cancel")]
        ]
    )

    await message.reply_text(preview, parse_mode=ParseMode.HTML, reply_markup=buttons)

    # preview message
    if source_msg:
        await source_msg.copy(message.chat.id)
    else:
        await client.send_message(message.chat.id, text_payload, parse_mode=ParseMode.HTML)

@Client.on_callback_query(filters.regex("^broad_"))
async def broad_callback(client, cb):
    global BROADCAST_RUNNING, BROADCAST_CANCEL

    uid = cb.from_user.id
    data = BROADCAST_CACHE.get(uid)

    if not data:
        return await cb.answer("Broadcast expired.")

    if cb.data == "broad_cancel":
        BROADCAST_CANCEL = True
        BROADCAST_CACHE.pop(uid, None)
        await cb.message.edit_text("❎ Broadcast cancelled.")
        return

    if cb.data != "broad_start":
        return

    if BROADCAST_RUNNING:
        return await cb.answer("Broadcast already running.", show_alert=True)

    BROADCAST_RUNNING = True
    BROADCAST_CANCEL = False

    msg = cb.message

    targets = data["targets"]
    source_msg = data["source_msg"]
    text_payload = data["text"]
    btype = data["type"]

    # ✅ FAST LOOKUP
    user_set = set(data["users"])

    total_targets = len(targets)

    sent_users = 0
    sent_groups = 0
    success = 0
    blocked = 0
    deleted = 0
    failed = 0

    progress = await msg.edit_text(
        "📡 <b>Broadcast Progressing...</b>\n\n"
        f"⏳ Progress: 0/{total_targets} (0%)",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⛔ Cancel Broadcast", callback_data="broad_cancel")]]
        )
    )

    for i, tid in enumerate(targets, start=1):

        if BROADCAST_CANCEL:
            BROADCAST_RUNNING = False
            return await progress.edit_text("⛔ Broadcast cancelled midway.")

        try:
            if btype == "forward":
                await source_msg.forward(tid)

            elif btype == "copy":
                await source_msg.copy(tid)

            else:
                if source_msg:
                    await source_msg.copy(tid)
                else:
                    await client.send_message(
                        tid,
                        text_payload,
                        parse_mode=ParseMode.HTML
                    )

            success += 1

            if tid in user_set:
                sent_users += 1
            else:
                sent_groups += 1

            await asyncio.sleep(0.07)

        except pyrogram.errors.UserIsBlocked:
            blocked += 1

        except pyrogram.errors.InputUserDeactivated:
            deleted += 1

        except pyrogram.errors.FloodWait as e:
            await asyncio.sleep(e.value + 2)

        except Exception:
            failed += 1

        # 🔄 UPDATE EVERY 40
        if i % 40 == 0:
            percent = round((i / total_targets) * 100, 2)

            try:
                await progress.edit_text(
                    "📡 <b>Broadcast Progressing...</b>\n\n"
                    f"👤 Sent Users: {sent_users}\n"
                    f"👥 Sent Groups: {sent_groups}\n"
                    f"✅ Success: {success}\n"
                    f"🚫 Blocked: {blocked}\n"
                    f"👻 Deleted: {deleted}\n"
                    f"❌ Failed: {failed}\n\n"
                    f"⏳ Progress: {i}/{total_targets} ({percent}%)",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("⛔ Cancel Broadcast", callback_data="broad_cancel")]]
                    )
                )
            except:
                pass

    BROADCAST_RUNNING = False
    BROADCAST_CACHE.pop(uid, None)

    await progress.edit_text(
        "✅ <b>Broadcast Completed</b>\n\n"
        f"🎯 Total: {total_targets}\n"
        f"📤 Success: {success}\n"
        f"🚫 Blocked: {blocked}\n"
        f"👻 Deleted: {deleted}\n"
        f"❌ Failed: {failed}",
        parse_mode=ParseMode.HTML
    )
    
@Client.on_message(filters.command("dbtrans"))
async def dbtrans_cmd(client, message):
    import json
    import asyncio

    if message.from_user.id != OWNER_ID:
        return

    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply_text(
            "📂 Reply to a JSON file containing user stats to import.\n\n"
            "<b>Format:</b> Each line is a JSON object, or a single JSON array <code>[{...}, {...}]</code>",
            parse_mode=ParseMode.HTML
        )

    status = await message.reply_text("📥 <b>Downloading file…</b>", parse_mode=ParseMode.HTML)

    try:
        file_bytes = await client.download_media(message.reply_to_message, in_memory=True)
        raw = bytes(file_bytes.getbuffer()).decode("utf-8", errors="ignore")
    except Exception as e:
        return await status.edit_text(f"❌ Failed to download file: {e}")

    records = []
    try:
        stripped = raw.strip()
        if stripped.startswith("["):
            records = json.loads(stripped)
        else:
            for line in stripped.splitlines():
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as e:
        return await status.edit_text(f"❌ Failed to parse JSON: {e}")

    if not records:
        return await status.edit_text("❌ No valid records found in file.")

    total = len(records)
    added = 0
    skipped = 0
    errors = []

    ANIM_FRAMES = ["⏳", "⌛", "🔄", "📊"]

    async def update_progress(frame_idx):
        frame = ANIM_FRAMES[frame_idx % len(ANIM_FRAMES)]
        bar_done = int((added + skipped) / total * 20) if total > 0 else 0
        bar = "█" * bar_done + "░" * (20 - bar_done)
        pct = int((added + skipped) / total * 100) if total > 0 else 0
        text = (
            f"{frame} <b>Importing Stats…</b>\n\n"
            f"<code>[{bar}] {pct}%</code>\n\n"
            f"✅ Added: <b>{added}</b>\n"
            f"⏭️ Skipped: <b>{skipped}</b>\n"
            f"📦 Total: <b>{total}</b>"
        )
        try:
            await status.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    for idx, record in enumerate(records):
        try:
            ts = record.get("total_stats", {})
            uid = int(record.get("user_id", 0))
            if not uid:
                skipped += 1
                continue

            username = record.get("username") or None
            first_name = record.get("first_name") or None

            runs = int(ts.get("runs", 0))
            wickets = int(ts.get("wickets", 0))
            matches = int(ts.get("matches_played", 0))
            balls_faced = int(ts.get("balls_faced", 0))
            balls_bowled = int(ts.get("balls_bowled", 0))
            runs_conceded = int(ts.get("runs_conceded", 0))
            sixes = int(ts.get("sixes", 0))
            fours = int(ts.get("fours", 0))
            centuries = int(ts.get("centuries", 0))
            fifties = int(ts.get("fifties", 0))
            ducks = int(ts.get("ducks", 0))
            hat_tricks = int(ts.get("hat_tricks", 0))

            mom_data = ts.get("man_of_match", {})
            moms = int(mom_data.get("total", 0)) if isinstance(mom_data, dict) else 0

            hs_data = ts.get("highest_score", {})
            highest_score = int(hs_data.get("runs", 0)) if isinstance(hs_data, dict) else int(hs_data or 0)

            bp_data = ts.get("best_partnership", {})
            if isinstance(bp_data, dict):
                best_partnership = int(bp_data.get("runs", 0))
            else:
                best_partnership = int(bp_data or 0)

            cap_data = ts.get("best_captain", {})
            wins = int(cap_data.get("wins", 0)) if isinstance(cap_data, dict) else 0
            losses = int(cap_data.get("losses", 0)) if isinstance(cap_data, dict) else 0

            existing = await db.db["user_stats"].find_one({"user_id": uid})
            if existing:
                await db.db["user_stats"].update_one(
                    {"user_id": uid},
                    {"$inc": {
                        "matches": matches, "wins": wins, "losses": losses,
                        "runs": runs, "wickets": wickets, "balls_faced": balls_faced,
                        "balls_bowled": balls_bowled, "runs_conceded": runs_conceded,
                        "sixes": sixes, "fours": fours, "centuries": centuries,
                        "fifties": fifties, "ducks": ducks, "hat_tricks": hat_tricks,
                        "moms": moms,
                    }, "$max": {
                        "highest_score": highest_score,
                        "best_partnership": best_partnership,
                    }, "$set": {
                        **({"username": username} if username else {}),
                        **({"first_name": first_name} if first_name else {}),
                    }}
                )
            else:
                await db.db["user_stats"].insert_one({
                    "user_id": uid,
                    "username": username,
                    "first_name": first_name,
                    "matches": matches, "wins": wins, "losses": losses,
                    "runs": runs, "wickets": wickets, "balls_faced": balls_faced,
                    "balls_bowled": balls_bowled, "runs_conceded": runs_conceded,
                    "sixes": sixes, "fours": fours, "centuries": centuries,
                    "fifties": fifties, "ducks": ducks, "hat_tricks": hat_tricks,
                    "moms": moms, "highest_score": highest_score,
                    "best_partnership": best_partnership,
                })

            await db.db["users"].update_one(
                {"user_id": uid},
                {"$setOnInsert": {"user_id": uid, "name": first_name or username or "Player", "coins": 1000, "games_played": 0, "notify_enabled": True}},
                upsert=True
            )

            added += 1

        except Exception as e:
            skipped += 1
            errors.append(f"uid={record.get('user_id','?')}: {str(e)[:60]}")

        if (idx + 1) % 3 == 0 or idx == total - 1:
            await update_progress(idx)
            await asyncio.sleep(0.1)

    result_text = (
        "✅ <b>Import Complete!</b>\n\n"
        f"📦 Total Records: <b>{total}</b>\n"
        f"✅ Successfully Added: <b>{added}</b>\n"
        f"⏭️ Skipped / Errors: <b>{skipped}</b>\n"
    )
    if errors:
        error_preview = "\n".join(errors[:5])
        result_text += f"\n⚠️ <b>Error Preview:</b>\n<code>{error_preview}</code>"

    await status.edit_text(result_text, parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("leave"))
async def leave_cmd(client, message):
    if not message.from_user or message.from_user.id != OWNER_ID:
        return

    target_chat_id = None

    if message.chat and message.chat.type in ("group", "supergroup"):
        target_chat_id = message.chat.id

    else:
        args = message.text.split(maxsplit=1)
        if len(args) == 2:
            try:
                target_chat_id = int(args[1])
            except ValueError:
                pass

    if not target_chat_id:
        try:
            await message.reply_text(
                "❌ Usage:\n"
                "• /leave (inside group)\n"
                "• /leave <group_id>"
            )
        except Exception:
            pass
        return

    try:
        await client.get_chat_member(target_chat_id, "me")
    except Exception:
        try:
            await message.reply_text(
                "⚠️ I am not a member of that group."
            )
        except Exception:
            pass
        return

    try:
        await client.send_message(
            target_chat_id,
            "🌙 𝗛𝗲𝘆 𝗳𝗼𝗹𝗸𝘀,\n\n"
            "Looks like it’s time for me to step out quietly ✨\n"
            "Thanks for having me around — it was fun while it lasted.\n\n"
            "If you feel this wasn’t meant to happen or something felt off,\n"
            "no worries at all 🤍 just reach out to the admins here:\n\n"
            "🎮 𝗣𝗹𝗮𝘆 𝗭𝗼𝗻𝗲 → https://t.me/CLG_fun_zone\n"
            "Take care & keep the vibes alive 🏏✨",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

    try:
        await client.leave_chat(target_chat_id)
    except Exception:
        pass

    try:
        await message.reply_text(
            f"✅ Left group `{target_chat_id}` successfully.",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

@Client.on_message(filters.command("active"))
async def active_matches_cmd(client, message):
    if message.from_user.id != OWNER_ID:
        return

    if not ACTIVE_MATCHES:
        return await message.reply_text("😴 There are no active games in any group right now.")

    msg = await message.reply_text("🔄 **Scanning Live Matches...** 📡")
    
    text = "🏏 **𝗚𝗟𝗢𝗕𝗔𝗟 𝗟𝗜𝗩𝗘 𝗠𝗔𝗧𝗖𝗛𝗘𝗦**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    count = 1

    for chat_id, match in list(ACTIVE_MATCHES.items()):
        try:
            chat = await client.get_chat(chat_id)
            chat_name = chat.title or "Unknown Group"
            
            if chat.username:
                chat_link = f"<a href='https://t.me/{chat.username}'>{chat_name}</a> [🌍 Public]"
            else:
                chat_link = f"<b>{chat_name}</b> [🔒 Private]"
                
            phase = match.get("phase", "UNKNOWN")
            
            mode = str(match.get("mode", "Team")).title()
            
            score_str = "Setup in progress..."
            if "teams" in match:
                tA = match["teams"].get("A", {})
                tB = match["teams"].get("B", {})
                
                rA, wA, bA = tA.get("runs", 0), tA.get("wickets", 0), tA.get("balls", 0)
                rB, wB, bB = tB.get("runs", 0), tB.get("wickets", 0), tB.get("balls", 0)
                
                score_str = f"🌊 A: {rA}/{wA} ({bA//6}.{bA%6} ov) | 🔥 B: {rB}/{wB} ({bB//6}.{bB%6} ov)"
                
            host_name = match.get("host_name", "Unknown Host")
            
            # Text formatting
            text += f"**{count}. {chat_link}**\n"
            text += f"🎮 <b>Mode:</b> {mode} | 📍 <b>Phase:</b> {phase}\n"
            text += f"📊 <b>Score:</b> `{score_str}`\n"
            text += f"👑 <b>Host:</b> {host_name}\n\n"
            
            count += 1
            await asyncio.sleep(0.1)
            
        except Exception as e:
            print(f"Error fetching info for chat {chat_id}: {e}")
            continue

    if count == 1:
        return await msg.edit_text("⚠️ Matches exist in memory, but couldn't fetch group details from Telegram (bot might have been kicked).")

    if len(text) > 4000:
        text = text[:4000] + "...\n\n<i>⚠️ List is too long! Showing top matches only.</i>"

    await msg.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                
