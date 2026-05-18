import time
import asyncio
import pyrogram.errors
from config import Config
from plugins.game.team import ACTIVE_MATCHES

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.connection import db
from database.users import total_users
from database.groups import total_groups

OWNER_ID = next(iter(Config.OWNER_IDS))
BROADCAST_CACHE = {}
BROADCAST_RUNNING = False
BROADCAST_CANCEL = False


async def _col():
    await db.ensure_pool()
    if db.db is None:
        raise RuntimeError("Database unavailable.")
    return db.db


@Client.on_message(filters.command("broad"))
async def broad_cmd(client, message):
    global BROADCAST_RUNNING

    from config import Config as _Config
    if _Config.IS_CLONE:
        return await message.reply_text(
            "🔒 <b>Broadcast is disabled in clone bots.</b>",
            parse_mode="html",
        )

    uid = message.from_user.id
    if uid != OWNER_ID:
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

    try:
        database = await _col()
        user_rows = await database["user_stats"].find({}, {"user_id": 1}).to_list(length=None)
        group_rows = await database["groups"].find({}, {"chat_id": 1}).to_list(length=None)
    except Exception as e:
        print("[BROADCAST DB ERROR]", e)
        return await message.reply_text("❌ Database not available.")

    users = list({u.get("user_id") for u in user_rows if u.get("user_id")})
    groups = list({g.get("chat_id") for g in group_rows if g.get("chat_id")})

    if not users and not groups:
        return await message.reply_text("⚠️ No users or groups found.")

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
        "groups": groups,
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
            [InlineKeyboardButton("❌ Cancel", callback_data="broad_cancel")],
        ]
    )

    await message.reply_text(preview, parse_mode=ParseMode.HTML, reply_markup=buttons)

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
    user_set = set(data["users"])
    total_targets = len(targets)

    sent_users = sent_groups = success = blocked = deleted = failed = 0

    progress = await msg.edit_text(
        "📡 <b>Broadcast Progressing...</b>\n\n"
        f"⏳ Progress: 0/{total_targets} (0%)",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⛔ Cancel Broadcast", callback_data="broad_cancel")]]
        ),
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
                    await client.send_message(tid, text_payload, parse_mode=ParseMode.HTML)

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
                    ),
                )
            except Exception:
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
        parse_mode=ParseMode.HTML,
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
            await message.reply_text("❌ Usage:\n• /leave (inside group)\n• /leave <group_id>")
        except Exception:
            pass
        return

    try:
        await client.get_chat_member(target_chat_id, "me")
    except Exception:
        try:
            await message.reply_text("⚠️ I am not a member of that group.")
        except Exception:
            pass
        return

    try:
        await client.send_message(
            target_chat_id,
            "🌙 𝗛𝗲𝘆 𝗳𝗼𝗹𝗸𝘀,\n\n"
            "Looks like it's time for me to step out quietly ✨\n"
            "Thanks for having me around — it was fun while it lasted.\n\n"
            f"📢 Updates: {Config.PLAY_ZONE_INFO}",
        )
    except Exception:
        pass

    try:
        await client.leave_chat(target_chat_id)
    except Exception:
        pass

    try:
        await message.reply_text(f"✅ Left group `{target_chat_id}` successfully.")
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

            status = match.get("status", "unknown")
            overs = match.get("overs", "?")
            host = match.get("host_name", "Unknown")
            players = len(match.get("players", []))

            text += (
                f"📌 <b>Match #{count}</b>\n"
                f"├ 🏟 Group: {chat_link}\n"
                f"├ 🆔 Chat ID: <code>{chat_id}</code>\n"
                f"├ 🎮 Status: <b>{status}</b>\n"
                f"├ 🎯 Overs: <b>{overs}</b>\n"
                f"├ 👑 Host: <b>{host}</b>\n"
                f"└ 👥 Players: <b>{players}</b>\n\n"
            )
            count += 1
        except Exception:
            continue

    text += f"━━━━━━━━━━━━━━━━━━━━━━\n📊 <b>Total Live Matches: {count - 1}</b>"

    try:
        await msg.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception:
        await message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
