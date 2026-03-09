import asyncio
import json
import os
import uuid
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus

from database.games import is_game_active, end_game as close_db_game
from plugins.game.team import ACTIVE_MATCHES
from plugins.game.team.over_engine import end_match
from plugins.utilities.logger import send_match_log
from plugins.game.team.lobby import REPLACEMENT_QUEUE

class MatchEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return str(obj)

async def is_host_or_admin(client, chat_id, user_id, host_id):
    if user_id == host_id:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            return True
    except:
        pass
    return False

@Client.on_message(filters.command("endgame") & filters.group)
async def end_game_command(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    match = ACTIVE_MATCHES.get(chat_id)

    if not match and not await is_game_active(chat_id):
        return await message.reply_text(
            "**𝗡𝗢 𝗔𝗖𝗧𝗜𝗩𝗘 𝗚𝗔𝗠𝗘**\n"
            "`Nothing to end.`"
        )

    host_id = match.get("host_id") if match else None

    if not await is_host_or_admin(client, chat_id, user_id, host_id):
        return await message.reply_text(
            "🚫 **Access Denied:** Only the Match Host or Group Admins can end the game."
        )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🛑 End Game", callback_data="confirm_endgame"),
                InlineKeyboardButton("✖ Cancel", callback_data="cancel_endgame"),
            ]
        ]
    )

    await message.reply_text(
        "⚠️ **𝗘𝗡𝗗 𝗚𝗔𝗠𝗘?**\n"
        "`This will force-end the match, create a backup file, and save stats.`",
        reply_markup=buttons
    )

@Client.on_callback_query(filters.regex("^confirm_endgame$"))
async def confirm_endgame(client, query):
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    group_title = query.message.chat.title or "Private Match"

    match = ACTIVE_MATCHES.get(chat_id)
    host_id = match.get("host_id") if match else None

    if not await is_host_or_admin(client, chat_id, user_id, host_id):
        return await query.answer(
            "🚫 Only the Match Host or Admins can click this.", show_alert=True
        )

    await query.answer("Force ending match & generating backup…")

    try:
        await query.message.edit_reply_markup(None)
    except:
        pass

    end_text = "🛑 **𝗚𝗔𝗠𝗘 𝗙𝗢𝗥𝗖𝗘 𝗘𝗡𝗗𝗘𝗗**\n`Match summary & stats saved.`"

    if match:
        try:
            for key, value in list(match.items()):
                if isinstance(value, asyncio.Task):
                    try:
                        value.cancel()
                    except:
                        pass

            if "timeouts" in match:
                for r in ["bowler", "batter"]:
                    task = match["timeouts"].get(r, {}).get("task")
                    if isinstance(task, asyncio.Task):
                        try:
                            task.cancel()
                        except:
                            pass
        except:
            pass

        safe_match = {}
        for key, val in match.items():
            if key in ["client", "timeouts", "cap_change_task"]:
                continue
            if isinstance(val, asyncio.Task):
                continue
            safe_match[key] = val

        file_name = f"match_backup_{chat_id}.json"

        try:
            with open(file_name, "w") as f:
                json.dump(safe_match, f, indent=4, cls=MatchEncoder)
        except:
            pass

        caption = (
            "💾 **𝗘𝗠𝗘𝗥𝗚𝗘𝗡𝗖𝗬 𝗠𝗔𝗧𝗖𝗛 𝗕𝗔𝗖𝗞𝗨𝗣**\n"
            "──┈┄┄╌╌╌╌┄┄┈──\n"
            "Game was force-ended. If this was a mistake, "
            "reply to this file with `/restore` to resume playing."
        )

        try:
            await client.send_document(chat_id, document=file_name, caption=caption)
        except:
            pass

        if os.path.exists(file_name):
            try:
                os.remove(file_name)
            except:
                pass

        match["client"] = client

        log_match = {
            "game_id": str(match.get("game_id", "Unknown")),
            "chat_id": chat_id,
            "host_id": match.get("host_id"),
            "host_name": match.get("host_name", "Unknown"),
        }

        balls_played = match.get("total_balls", 0)
        early_force_end = balls_played < 6

        try:
            await end_match(match, forced=True)
        except:
            pass

        if early_force_end:
            end_text = (
                "🛑 **𝗚𝗔𝗠𝗘 𝗙𝗢𝗥𝗖𝗘 𝗘𝗡𝗗𝗘𝗗**\n"
                "`Match stopped early. Player stats saved.`"
            )

        try:
            await send_match_log(
                client,
                "🛑 MATCH FORCE ENDED",
                log_match,
                f"Match was force ended by {query.from_user.mention} in {group_title}.\n💾 A JSON backup was generated.",
            )
        except:
            pass

    try:
        await close_db_game(chat_id)
    except:
        pass

    try:
        REPLACEMENT_QUEUE.pop(chat_id, None)
    except:
        pass

    ACTIVE_MATCHES.pop(chat_id, None)

    try:
        await query.message.edit_text(end_text)
    except:
        try:
            await query.message.delete()
            await client.send_message(chat_id, end_text)
        except:
            pass
            
@Client.on_callback_query(filters.regex("^cancel_endgame$"))
async def cancel_endgame(client, query):
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    match = ACTIVE_MATCHES.get(chat_id)
    host_id = match.get("host_id") if match else None

    if not await is_host_or_admin(client, chat_id, user_id, host_id):
        return await query.answer(
            "🚫 Only the Match Host or Admins can do this.", show_alert=True
        )

    await query.answer("Cancelled")

    try:
        await query.message.delete()
    except:
        pass
