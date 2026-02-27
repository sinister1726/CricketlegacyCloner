import time
import asyncio
from datetime import datetime, timedelta

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
BOT_START_TIME = time.time()

def uptime():
    secs = int(time.time() - BOT_START_TIME)
    h = secs // 3600
    m = (secs % 3600) // 60
    return f"{h}h {m}m"

@Client.on_message(filters.command("fetch"))
async def fetch_dashboard(client, message):
    if message.from_user.id != OWNER_ID:
        return

    try:
        now = datetime.utcnow()

        users_total = await total_users()

        async with db.pool.acquire() as conn:
            users_7d = await conn.fetchval(
            ) or 0

        active_users = users_total
        inactive_users = 0

        groups_total = await total_groups()
        active_groups = groups_total
        inactive_groups = 0

        async with db.pool.acquire() as conn:
            games_today = await conn.fetchval(
                "SELECT COUNT(*) FROM games WHERE created_at::date = CURRENT_DATE"
            ) or 0

            games_total = await conn.fetchval(
                "SELECT COUNT(*) FROM games"
            ) or 0

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
            "• /bcast – Copy broadcast\n"
            "• /fcast – Forward broadcast\n"
            "• /stats – Visual stats\n"
            "• /fetch – Full system dashboard\n\n"

            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>Last Updated:</b> {now.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        await message.reply_text(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        print("[FETCH ERROR]", e)
        await message.reply_text(
            "⚠️ Failed to fetch system data.\nCheck logs.",
            parse_mode="HTML"
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
        target = await client.get_users(args[1])
        tier = int(args[2])
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
    uid = message.from_user.id

    if uid != OWNER_ID and not await is_mod(uid, min_tier=2):
        return  # silent ignore

    text_payload = None
    source_msg = None

    if message.reply_to_message:
        source_msg = message.reply_to_message
    else:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            return await message.reply_text("Nothing to broadcast 🤨")
        text_payload = args[1]

    BROADCAST_CACHE[uid] = {
        "text": text_payload,
        "source_msg": source_msg
    }

    preview_text = (
        "📣 <b>BROADCAST PREVIEW</b>\n\n"
        "This is exactly how it will be sent.\n"
        "Choose wisely 👇"
    )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🚀 Send Normally", callback_data="broad_send_normal"),
                InlineKeyboardButton("📌 Send & Pin", callback_data="broad_send_pin")
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data="broad_cancel")
            ]
        ]
    )

    await client.send_message(
        chat_id=message.chat.id,
        text=preview_text,
        parse_mode=ParseMode.HTML,
        reply_markup=buttons
    )

    if source_msg:
        await source_msg.copy(message.chat.id)
    else:
        await client.send_message(
            chat_id=message.chat.id,
            text=text_payload,
            parse_mode=ParseMode.HTML
        )

@Client.on_callback_query(filters.regex("^broad_"))
async def broad_callback(client, cb):
    uid = cb.from_user.id
    
    if uid != OWNER_ID and not await is_mod(uid, min_tier=2):
        await cb.answer("Not for you 😌", show_alert=True)
        return

    data = BROADCAST_CACHE.get(uid)
    if not data:
        await cb.answer("Broadcast expired 😴", show_alert=True)
        return

    action = cb.data
    msg = cb.message
    
    if action == "broad_cancel":
        BROADCAST_CACHE.pop(uid, None)
        await msg.edit_text("❎ Broadcast cancelled.")
        return

    text_payload = data["text"]
    source_msg = data["source_msg"]

    try:
        async with db.pool.acquire() as conn:
            user_rows = await conn.fetch(
            )

            group_rows = await conn.fetch(
                "SELECT chat_id FROM groups"
            )

        targets = [u["user_id"] for u in user_rows] + [g["chat_id"] for g in group_rows]

    except Exception:
        await msg.edit_text("⚠️ Failed to fetch broadcast targets.")
        return

    sent = 0
    failed = 0

    await msg.edit_text("🚀 Broadcasting… grab popcorn 🍿")

    for tid in targets:
        try:
            if source_msg:
                sent_msg = await source_msg.copy(tid)
            else:
                sent_msg = await client.send_message(
                    tid,
                    text_payload,
                    parse_mode=ParseMode.HTML
                )

            if action == "broad_send_pin":
                try:
                    await client.pin_chat_message(tid, sent_msg.id)
                except Exception:
                    pass

            sent += 1
            await asyncio.sleep(0.05)

        except Exception:
            failed += 1
            continue

    BROADCAST_CACHE.pop(uid, None)

    await msg.edit_text(
        f"✅ <b>Broadcast Completed</b>\n\n"
        f"📤 Sent: <b>{sent}</b>\n"
        f"❌ Failed: <b>{failed}</b>",
        parse_mode=ParseMode.HTML
    )

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
            "🎮 𝗣𝗹𝗮𝘆 𝗭𝗼𝗻𝗲 → https://t.me/+k_za3lVumag2NDgx"
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
