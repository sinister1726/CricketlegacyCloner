import asyncio
import time
import uuid
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.connection import db
from database.games import (
    get_active_game,
    end_game as close_db_game,
    user_in_other_game,
)
from plugins.game.team import ACTIVE_MATCHES
from Assets.files import MEMBERS_IMAGE, SOLO_MODE_IMAGE
from pyrogram.types import InputMediaPhoto
from utils.guards import is_group_admin, ensure_user

SOLO_JOIN_SECONDS = 120
MIN_PLAYERS = 3


def _fresh_player_stats():
    return {
        "runs": 0,
        "balls_faced": 0,
        "is_out": False,
        "batting_balls": [],
        "bowling_balls": [],
        "wickets": 0,
        "runs_conceded": 0,
        "balls_bowled": 0,
        "fours_count": 0,
        "sixes_count": 0,
    }


async def _ensure_user_exists(user):
    await ensure_user(user)


async def _is_admin(client, chat_id, user_id):
    return await is_group_admin(client, chat_id, user_id)


@Client.on_callback_query(filters.regex("^mode_solo$"))
async def solo_mode_selected(client, query):
    await query.answer()
    chat_id = query.message.chat.id
    user = query.from_user

    existing, other = await asyncio.gather(
        get_active_game(chat_id),
        user_in_other_game(user.id, chat_id),
    )

    if existing:
        return await query.answer("⚠️ A game is already running here.", show_alert=True)
    if other:
        return await query.answer("⚠️ You are already in another game.", show_alert=True)

    game_id = str(uuid.uuid4())
    group_title = query.message.chat.title or "Cricket Arena"
    join_ends_at = time.time() + SOLO_JOIN_SECONDS

    ACTIVE_MATCHES[chat_id] = {
        "chat_id": chat_id,
        "game_id": game_id,
        "host_id": user.id,
        "host_name": user.first_name,
        "client": client,
        "mode": "Solo",
        "phase": "SOLO_JOIN",
        "players": [user.id],
        "user_cache": {user.id: user.first_name or "Player"},
        "username_cache": {user.id: user.username or user.first_name or "Player"},
        "player_stats": {user.id: _fresh_player_stats()},
        "current_batter": None,
        "current_bowler": None,
        "bowler_rotation_pos": 1,
        "balls_in_spell": 0,
        "total_runs": 0,
        "total_wickets": 0,
        "total_balls": 0,
        "bowled": False,
        "batted": False,
        "last_bowl": None,
        "prompt_dispatched": False,
        "join_ends_at": join_ends_at,
        "join_timer_task": None,
        "timeouts": {
            "bowler": {"fails": 0, "task": None},
            "batter": {"fails": 0, "task": None},
        },
        "last_active": time.time(),
        "announced_achievements": {"batting": {}, "bowling": {}},
        "timeout_strikes": {},
        "eliminated_player_ids": set(),
    }
    match = ACTIVE_MATCHES[chat_id]

    solo_caption = (
        "👤 <b>𝗦𝗢𝗟𝗢 𝗠𝗢𝗗𝗘 𝗦𝗘𝗟𝗘𝗖𝗧𝗘𝗗</b>\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n\n"
        "📢 Join using /joingame\n"
        "📤 Leave using /leavegame\n"
        f"⏳ Lobby closes in <b>{SOLO_JOIN_SECONDS // 60} minutes</b>.\n"
        "⚡ Minimum <b>3 players</b> required to start.\n\n"
        "🔧 Admins: <code>/extend 30</code> | <code>/forcestart</code>"
    )
    try:
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=SOLO_MODE_IMAGE,
                caption=solo_caption,
                parse_mode=ParseMode.HTML,
            )
        )
    except Exception:
        try:
            await query.message.edit_caption(
                caption=solo_caption,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await client.send_message(
                chat_id,
                "👤 <b>𝗦𝗢𝗟𝗢 𝗠𝗢𝗗𝗘</b> — Join via /joingame\n"
                f"⏳ Closes in {SOLO_JOIN_SECONDS // 60} min | Min 3 players",
                parse_mode=ParseMode.HTML,
            )

    match["join_timer_task"] = asyncio.create_task(_solo_join_timer(client, chat_id))
    asyncio.create_task(_create_solo_game_db(game_id, chat_id, group_title, user))


async def _create_solo_game_db(game_id, chat_id, group_title, user):
    try:
        existing_game = await db.db["games"].find_one({"game_id": game_id})
        if not existing_game:
            await db.db["games"].insert_one({
                "game_id": game_id, "chat_id": chat_id, "title": group_title,
                "mode": "solo", "host_id": user.id, "status": "active", "phase": "SOLO_JOIN",
            })
        await _ensure_user_exists(user)
        existing_gp = await db.db["game_players"].find_one({"game_id": game_id, "user_id": user.id})
        if not existing_gp:
            await db.db["game_players"].insert_one({"game_id": game_id, "user_id": user.id, "team": "S"})
    except Exception as e:
        print(f"Solo game DB create (bg) error: {e}")


@Client.on_message(filters.command("joingame") & filters.group)
async def join_solo_game(client, message):
    chat_id = message.chat.id
    user = message.from_user
    match = ACTIVE_MATCHES.get(chat_id)

    if not match or match.get("mode") != "Solo":
        return await message.reply_text("😴 No solo lobby right now. Start one with /start")

    if match.get("phase") != "SOLO_JOIN":
        return await message.reply_text("🔒 Lobby is closed. Game is in progress.")

    if user.id in match["players"]:
        return await message.reply_text("😏 You're already in the lobby.")

    from plugins.game.solo import is_solo_banned, ban_remaining_seconds
    if is_solo_banned(chat_id, user.id):
        secs = ban_remaining_seconds(chat_id, user.id)
        mins = secs // 60
        s = secs % 60
        return await message.reply_text(
            f"🔴 <b>You are temporarily banned from Solo games in this group.</b>\n"
            f"⏳ Ban expires in <b>{mins}m {s}s</b>.\n"
            "Reason: Too many timeout eliminations.",
            parse_mode=ParseMode.HTML,
        )

    other = await user_in_other_game(user.id, chat_id)
    if other:
        return await message.reply_text(
            f"⚠️ You're already in <b>{other['title']}</b>. Finish that first.",
            parse_mode=ParseMode.HTML,
        )

    match["players"].append(user.id)
    match["user_cache"][user.id] = user.first_name or "Player"
    match["username_cache"][user.id] = user.username or user.first_name or "Player"
    match["player_stats"][user.id] = _fresh_player_stats()

    asyncio.create_task(_join_solo_game_db(match["game_id"], user))

    count = len(match["players"])
    needed = max(0, MIN_PLAYERS - count)
    suffix = f" — {needed} more needed!" if needed > 0 else " — ready to start! ✅"
    await message.reply_text(
        f"✅ <b>{user.first_name}</b> joined! ({count} player{'s' if count != 1 else ''}){suffix}",
        parse_mode=ParseMode.HTML,
    )


async def _join_solo_game_db(game_id, user):
    try:
        await _ensure_user_exists(user)
        existing = await db.db["game_players"].find_one({"game_id": game_id, "user_id": user.id})
        if not existing:
            await db.db["game_players"].insert_one({"game_id": game_id, "user_id": user.id, "team": "S"})
    except Exception as e:
        print(f"Solo join DB (bg) error: {e}")


@Client.on_message(filters.command("leavegame") & filters.group)
async def leave_solo_game(client, message):
    chat_id = message.chat.id
    user = message.from_user
    match = ACTIVE_MATCHES.get(chat_id)

    if not match or match.get("mode") != "Solo":
        return

    if match.get("phase") != "SOLO_JOIN":
        return await message.reply_text("🏏 Can't leave during a live game.")

    if user.id not in match["players"]:
        return await message.reply_text("You're not in the lobby.")

    match["players"].remove(user.id)
    match["user_cache"].pop(user.id, None)
    match.get("username_cache", {}).pop(user.id, None)
    match["player_stats"].pop(user.id, None)

    asyncio.create_task(_leave_solo_game_db(match["game_id"], user.id))

    count = len(match["players"])
    await message.reply_text(
        f"👋 <b>{user.first_name}</b> left. ({count} remaining)",
        parse_mode=ParseMode.HTML,
    )


async def _leave_solo_game_db(game_id, user_id):
    try:
        await db.db["game_players"].delete_one({"game_id": game_id, "user_id": user_id})
    except Exception as e:
        print(f"Solo leave DB (bg) error: {e}")


@Client.on_message(filters.command("extend") & filters.group)
async def extend_solo_lobby(client, message):
    chat_id = message.chat.id
    user = message.from_user
    match = ACTIVE_MATCHES.get(chat_id)

    if not match or match.get("mode") != "Solo":
        return await message.reply_text("❌ No solo lobby to extend.")

    if match.get("phase") != "SOLO_JOIN":
        return await message.reply_text("❌ Game already started.")

    if not await _is_admin(client, chat_id, user.id):
        return await message.reply_text("🚫 Admins only.")

    args = message.text.split()
    try:
        extra = int(args[1]) if len(args) > 1 else 30
        extra = max(10, min(extra, 300))  # clamp 10–300 seconds
    except (ValueError, IndexError):
        extra = 30

    old_ends = match.get("join_ends_at", time.time())
    match["join_ends_at"] = old_ends + extra

    # Cancel old timer and restart from remaining deadline
    old_task = match.get("join_timer_task")
    if old_task and not old_task.done():
        old_task.cancel()

    match["join_timer_task"] = asyncio.create_task(_solo_join_timer(client, chat_id))

    remaining = int(match["join_ends_at"] - time.time())
    await message.reply_text(
        f"⏰ <b>Lobby extended by {extra}s!</b>\n"
        f"⏳ New time remaining: <b>{remaining}s</b>",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.command("forcestart") & filters.group)
async def forcestart_solo(client, message):
    chat_id = message.chat.id
    user = message.from_user
    match = ACTIVE_MATCHES.get(chat_id)

    if not match or match.get("mode") != "Solo":
        return await message.reply_text("❌ No solo lobby to force-start.")

    if match.get("phase") != "SOLO_JOIN":
        return await message.reply_text("❌ Game already started.")

    if not await _is_admin(client, chat_id, user.id):
        return await message.reply_text("🚫 Admins only.")

    count = len(match["players"])
    if count < MIN_PLAYERS:
        return await message.reply_text(
            f"❌ <b>Not enough players!</b>\n"
            f"You have <b>{count}</b>, need at least <b>{MIN_PLAYERS}</b>.\n"
            "Tell more people to /joingame!",
            parse_mode=ParseMode.HTML,
        )

    # Cancel the join timer so it doesn't trigger again
    old_task = match.get("join_timer_task")
    if old_task and not old_task.done():
        old_task.cancel()

    await message.reply_text(
        f"⚡ <b>Force starting with {count} players!</b>",
        parse_mode=ParseMode.HTML,
    )
    await start_solo_game(client, chat_id)


async def _solo_join_timer(client, chat_id):
    """Deadline-based join timer. Reads match['join_ends_at'] dynamically so /extend works."""
    try:
        while True:
            match = ACTIVE_MATCHES.get(chat_id)
            if not match or match.get("phase") != "SOLO_JOIN":
                return

            now = time.time()
            deadline = match.get("join_ends_at", now)
            remaining = deadline - now

            if remaining <= 0:
                break

            if remaining > 60:
                # Sleep until 60s before deadline
                await asyncio.sleep(remaining - 60)
                match = ACTIVE_MATCHES.get(chat_id)
                if not match or match.get("phase") != "SOLO_JOIN":
                    return
                remaining = match["join_ends_at"] - time.time()
                if remaining > 0:
                    try:
                        await client.send_message(
                            chat_id,
                            f"⏳ <b>1 minute left</b> to join!\n"
                            f"Players: <b>{len(match['players'])}</b> | "
                            f"Need: <b>{MIN_PLAYERS}</b>\n📢 /joingame",
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        pass

            elif remaining > 10:
                # Sleep until 10s before deadline
                await asyncio.sleep(remaining - 10)
                match = ACTIVE_MATCHES.get(chat_id)
                if not match or match.get("phase") != "SOLO_JOIN":
                    return
                remaining = match["join_ends_at"] - time.time()
                if remaining > 0:
                    try:
                        await client.send_message(
                            chat_id,
                            f"⚠️ <b>10 seconds left!</b> Last chance → /joingame",
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        pass

            else:
                # In the final 10s, just sleep the rest
                await asyncio.sleep(max(0.5, remaining))
                break

        # Final check at deadline
        match = ACTIVE_MATCHES.get(chat_id)
        if not match or match.get("phase") != "SOLO_JOIN":
            return

        # One last check if deadline was extended while we were in the final sleep
        if match["join_ends_at"] - time.time() > 2:
            # Deadline was extended — restart timer
            match["join_timer_task"] = asyncio.create_task(_solo_join_timer(client, chat_id))
            return

        count = len(match["players"])
        if count < MIN_PLAYERS:
            await client.send_message(
                chat_id,
                f"❌ <b>Game Cancelled!</b>\n"
                f"Only <b>{count}</b> joined. Need at least <b>{MIN_PLAYERS}</b>.",
                parse_mode=ParseMode.HTML,
            )
            ACTIVE_MATCHES.pop(chat_id, None)
            await close_db_game(chat_id)
            return

        await start_solo_game(client, chat_id)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Solo join timer error: {e}")


async def start_solo_game(client, chat_id):
    match = ACTIVE_MATCHES.get(chat_id)
    if not match:
        return

    match["phase"] = "LIVE"
    match["current_batter"] = match["players"][0]
    match["bowler_rotation_pos"] = 1

    from plugins.game.solo import get_next_solo_bowler
    match["current_bowler"] = get_next_solo_bowler(match)
    match["balls_in_spell"] = 0

    players = match["players"]
    user_cache = match["user_cache"]
    batter_name = user_cache.get(match["current_batter"], "Player")
    bowler_name = user_cache.get(match["current_bowler"], "Player")

    player_list = "\n".join(
        f"{i+1}. {user_cache.get(uid, 'Player')}" for i, uid in enumerate(players)
    )

    asyncio.create_task(_update_game_phase_db(chat_id, "LIVE"))

    await client.send_message(
        chat_id,
        f"🏏 <b>𝗦𝗢𝗟𝗢 𝗖𝗥𝗜𝗖𝗞𝗘𝗧 𝗕𝗘𝗚𝗜𝗡𝗦!</b>\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"👥 <b>Players ({len(players)}):</b>\n{player_list}\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"🏏 <b>First Batter:</b> {batter_name}\n"
        f"⚾ <b>First Bowler:</b> {bowler_name}\n\n"
        "🎯 No dot balls (0) | Same number = OUT ⚡",
        parse_mode=ParseMode.HTML,
    )

    await asyncio.sleep(0.8)
    await client.send_message(chat_id, f"🎉 {batter_name}, you're batting first!", parse_mode=ParseMode.HTML)
    await asyncio.sleep(0.8)
    await client.send_message(chat_id, f"🎯 {bowler_name}, you bowl first!", parse_mode=ParseMode.HTML)

    from plugins.game.solo.state import send_solo_ball_prompt
    await send_solo_ball_prompt(client, match)


async def _update_game_phase_db(chat_id, phase):
    try:
        await db.db["games"].update_one({"chat_id": chat_id, "status": "active"}, {"$set": {"phase": phase}})
    except Exception as e:
        print(f"Solo phase DB update error: {e}")
