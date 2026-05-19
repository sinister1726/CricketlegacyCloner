import asyncio
import random
import time
import html
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, MessageNotModified

from database.connection import db
from utils.media_helper import get_video_file_id

MATCHMAKING_QUEUE = {}
DUEL_MATCHES = {}
USER_IN_DUEL = {}

QUEUE_TIMEOUT = 120

BALL_BUTTONS = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("1️⃣", callback_data="duel_pick:1"),
        InlineKeyboardButton("2️⃣", callback_data="duel_pick:2"),
        InlineKeyboardButton("3️⃣", callback_data="duel_pick:3"),
    ],
    [
        InlineKeyboardButton("4️⃣", callback_data="duel_pick:4"),
        InlineKeyboardButton("5️⃣", callback_data="duel_pick:5"),
        InlineKeyboardButton("6️⃣", callback_data="duel_pick:6"),
    ],
])

DUEL_INTROS = [
    "⚔️ <b>THE DUEL BEGINS!</b>\nTwo legends. One pitch. No mercy.",
    "🏟️ <b>MATCH LOCKED IN!</b>\nMay the best batter win.",
    "🔥 <b>GAME ON!</b>\nMatch your number to dismiss — or score big!",
]

RUN_COMMENTS = {
    1: ["Quick single! Strike rotated.", "Nudged away for one.", "Sharp running — one run!"],
    2: ["Placed nicely — two runs! 🏃", "Easy two off that.", "Good placement, two runs!"],
    3: ["Three! Brave running 💨", "Pushed to deep — three runs!", "Risky but rewarding!"],
    4: ["FOUR! 🔥 Raced to the fence!", "BOUNDARY! Lovely shot 🎯", "Cracked through covers — FOUR!"],
    5: ["Five runs! Chaos in the field 😵", "Overthrows! They steal five! 🏃‍♂️", "Misfield madness — five runs!"],
    6: ["SIX! 🚀 Gone into the stands!", "MAXIMUM! 💥 What a hit!", "MONSTROUS! That's in orbit! 🌌"],
}

OUT_COMMENTS = [
    "💀 OUT! Numbers matched — bowler wins this ball!",
    "🎯 BOWLED! Same number — that's a wicket!",
    "👆 OUT! The trap worked perfectly!",
    "❌ OUT! Guessed right — batter walks back!",
]


def _mention(uid, name):
    return f"<a href='tg://user?id={uid}'>{html.escape(str(name))}</a>"


def _match_key(a, b):
    return f"{min(a,b)}_{max(a,b)}"


async def _safe_send_video(client, chat_id, video_key, caption):
    from utils.media_helper import send_video_or_fallback
    # Fall back to key "1" if the requested key has no media
    from Assets.files import RUN_VIDEOS
    if not RUN_VIDEOS.get(str(video_key)):
        video_key = "1"
    return await send_video_or_fallback(client, chat_id, "run", video_key, caption)


async def _safe_delete(client, chat_id, msg_id):
    if not msg_id:
        return
    try:
        await client.delete_messages(chat_id, msg_id)
    except Exception:
        pass


async def _send_ball_prompt(client, match):
    phase = match["phase"]
    if phase == "a_batting":
        batter_id, bowler_id = match["player_a"], match["player_b"]
        batter_name, bowler_name = match["name_a"], match["name_b"]
        score = match["a_score"]
        balls = match["a_balls"]
    else:
        batter_id, bowler_id = match["player_b"], match["player_a"]
        batter_name, bowler_name = match["name_b"], match["name_a"]
        score = match["b_score"]
        balls = match["b_balls"]

    match["pending_bat_choice"] = None
    match["pending_bowl_choice"] = None

    bat_txt = (
        f"🏏 <b>Your Turn — BATTING</b>\n"
        f" ❖ <b>{html.escape(batter_name)}</b>: {score} ({balls}b)\n\n"
        f"Pick your shot number 👇\n"
        f"<i>Tip: If your number matches the bowler's — OUT!</i>"
    )

    bowl_txt = (
        f"🎯 <b>Your Turn — BOWLING</b>\n"
        f" ❖ Bowling to <b>{html.escape(batter_name)}</b>: {score} ({balls}b)\n\n"
        f"Pick your delivery number 👇\n"
        f"<i>Tip: Match the batter's number to take a wicket!</i>"
    )

    if phase == "b_batting" and match.get("a_score") is not None:
        target = match["a_score"] + 1
        bat_txt = (
            f"🏏 <b>Your Turn — BATTING</b>\n"
            f"👤 <b>{html.escape(batter_name)}</b>: {score} ({balls}b)\n"
            f"➥ Target: <b>{target}</b> runs\n\n"
            f"Pick your shot number 👇"
        )

    bat_msg = await client.send_message(batter_id, bat_txt, parse_mode=ParseMode.HTML, reply_markup=BALL_BUTTONS)
    bowl_msg = await client.send_message(bowler_id, bowl_txt, parse_mode=ParseMode.HTML, reply_markup=BALL_BUTTONS)

    if phase == "a_batting":
        match["last_prompt_a"] = bat_msg.id if bat_msg else None
        match["last_prompt_b"] = bowl_msg.id if bowl_msg else None
    else:
        match["last_prompt_b"] = bat_msg.id if bat_msg else None
        match["last_prompt_a"] = bowl_msg.id if bowl_msg else None


async def _process_ball(client, match):
    bat_choice = match["pending_bat_choice"]
    bowl_choice = match["pending_bowl_choice"]
    phase = match["phase"]

    if phase == "a_batting":
        batter_id, bowler_id = match["player_a"], match["player_b"]
        batter_name, bowler_name = match["name_a"], match["name_b"]
    else:
        batter_id, bowler_id = match["player_b"], match["player_a"]
        batter_name, bowler_name = match["name_b"], match["name_a"]

    is_out = (bat_choice == bowl_choice)

    if is_out:
        comment = random.choice(OUT_COMMENTS)
        result_line = f"🏏 <b>{html.escape(batter_name)}</b> chose <b>{bat_choice}</b> — 🎯 <b>{html.escape(bowler_name)}</b> chose <b>{bowl_choice}</b>\n{comment}"
        video_key = "Out"
    else:
        runs = bat_choice
        comment = random.choice(RUN_COMMENTS.get(runs, ["Nice shot!"]))
        result_line = f"🏏 <b>{html.escape(batter_name)}</b> chose <b>{bat_choice}</b> — 🎯 <b>{html.escape(bowler_name)}</b> chose <b>{bowl_choice}</b>\n{comment}"
        video_key = str(runs)

    for uid in [match["player_a"], match["player_b"]]:
        prev_key = "last_vid_a" if uid == match["player_a"] else "last_vid_b"
        await _safe_delete(client, uid, match.get(prev_key))

    msg_a = await _safe_send_video(client, match["player_a"], video_key, result_line)
    msg_b = await _safe_send_video(client, match["player_b"], video_key, result_line)
    match["last_vid_a"] = msg_a.id if msg_a else None
    match["last_vid_b"] = msg_b.id if msg_b else None

    if not is_out:
        runs = bat_choice
        if phase == "a_batting":
            match["a_score"] += runs
            match["a_balls"] += 1
            match["a_wickets"] = match.get("a_wickets", 0)
        else:
            match["b_score"] += runs
            match["b_balls"] += 1

        if phase == "b_batting":
            target = match["a_score"] + 1
            if match["b_score"] >= target:
                await _end_duel(client, match, winner="b")
                return

        await asyncio.sleep(1.5)
        await _send_ball_prompt(client, match)
    else:
        if phase == "a_batting":
            match["a_balls"] += 1
            await asyncio.sleep(1.5)
            await _start_b_batting(client, match)
        else:
            match["b_balls"] += 1
            await asyncio.sleep(1.5)
            await _end_duel(client, match, winner="a")


async def _start_b_batting(client, match):
    a_score = match["a_score"]
    a_balls = match["a_balls"]
    name_a = match["name_a"]
    name_b = match["name_b"]

    transition = (
        f"🏏 <b>Innings Break!</b>\n\n"
        f"<b>{html.escape(name_a)}</b> scored <b>{a_score}</b> runs in {a_balls} balls.\n"
        f"🎯 <b>{html.escape(name_b)}</b> needs <b>{a_score + 1}</b> to win!\n\n"
        f"Get ready — <b>{html.escape(name_b)}</b> bats now!"
    )

    await client.send_message(match["player_a"], transition, parse_mode=ParseMode.HTML)
    await client.send_message(match["player_b"], transition, parse_mode=ParseMode.HTML)

    match["phase"] = "b_batting"
    match["b_score"] = 0
    match["b_balls"] = 0
    match["pending_bat_choice"] = None
    match["pending_bowl_choice"] = None

    await asyncio.sleep(2)
    await _send_ball_prompt(client, match)


async def _end_duel(client, match, winner):
    match["phase"] = "finished"
    key = _match_key(match["player_a"], match["player_b"])

    uid_a = match["player_a"]
    uid_b = match["player_b"]
    name_a = match["name_a"]
    name_b = match["name_b"]

    if winner == "a":
        winner_id, loser_id = uid_a, uid_b
        winner_name, loser_name = name_a, name_b
        winner_score = match["a_score"]
        loser_score = match["b_score"]
    else:
        winner_id, loser_id = uid_b, uid_a
        winner_name, loser_name = name_b, name_a
        winner_score = match["b_score"]
        loser_score = match["a_score"]

    result_text = (
        f" ❖ <b>DUEL OVER!</b>\n\n"
        f"🥇 <b>WINNER:</b> {html.escape(winner_name)}\n"
        f"➥ Score: <b>{winner_score}</b> runs\n\n"
        f"😔 <b>Defeated:</b> {html.escape(loser_name)}\n"
        f"➥ Score: <b>{loser_score}</b> runs\n\n"
        "🎮 GG! Play again in your group with /start"
    )

    await client.send_message(uid_a, result_text, parse_mode=ParseMode.HTML)
    await client.send_message(uid_b, result_text, parse_mode=ParseMode.HTML)

    DUEL_MATCHES.pop(key, None)
    USER_IN_DUEL.pop(uid_a, None)
    USER_IN_DUEL.pop(uid_b, None)

    asyncio.create_task(_save_duel_stats(match, winner_id, loser_id))
    asyncio.create_task(_send_duel_log(client, match, winner_name, loser_name, winner_score, loser_score))


async def _save_duel_stats(match, winner_id, loser_id):
    try:
        uid_a = match["player_a"]
        uid_b = match["player_b"]
        a_score = match["a_score"]
        b_score = match["b_score"]
        a_balls = match["a_balls"]
        b_balls = match["b_balls"]
        a_duck = 1 if a_score == 0 else 0
        b_duck = 1 if b_score == 0 else 0

        a_wickets = 1
        b_wickets = 1 if match["phase"] == "finished" and winner_id == uid_a else 0

        for uid, score, wickets, duck, is_win in [
            (uid_a, a_score, a_wickets, a_duck, winner_id == uid_a),
            (uid_b, b_score, b_wickets, b_duck, winner_id == uid_b),
        ]:
            existing = await db.db["duel_stats"].find_one({"user_id": uid})
            if existing:
                await db.db["duel_stats"].update_one(
                    {"user_id": uid},
                    {"$inc": {
                        "matches": 1,
                        "wins": 1 if is_win else 0,
                        "losses": 0 if is_win else 1,
                        "runs": score,
                        "wickets": wickets,
                        "ducks": duck,
                    }, "$max": {"highest_score": score}}
                )
            else:
                await db.db["duel_stats"].insert_one({
                    "user_id": uid,
                    "matches": 1,
                    "wins": 1 if is_win else 0,
                    "losses": 0 if is_win else 1,
                    "runs": score,
                    "wickets": wickets,
                    "highest_score": score,
                    "ducks": duck,
                })
    except Exception as e:
        print(f"Duel stats save error: {e}")


async def _queue_timeout(uid, name, client):
    await asyncio.sleep(QUEUE_TIMEOUT)
    if uid in MATCHMAKING_QUEUE:
        MATCHMAKING_QUEUE.pop(uid, None)
        try:
            await client.send_message(
                uid,
                "⏱️ <b>Matchmaking Cancelled</b>\n\nNo opponent found in 2 minutes.\nTry again from your group! 🏏",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass


@Client.on_callback_query(filters.regex("^mode_duel$"))
async def duel_group_redirect(client, query):
    if query.message.chat.type.name == "PRIVATE":
        await query.answer("Use this in a group chat!", show_alert=True)
        return

    me = await client.get_me()
    url = f"https://t.me/{me.username}?start=duel"
    await query.answer(url=url)


@Client.on_callback_query(filters.regex("^duel_ready$"))
async def duel_ready(client, query):
    uid = query.from_user.id
    name = query.from_user.first_name or "Player"

    if uid in USER_IN_DUEL:
        await query.answer("You're already in a duel!", show_alert=True)
        return

    if uid in MATCHMAKING_QUEUE:
        await query.answer("You're already in the queue!", show_alert=True)
        return

    other_uid = None
    for q_uid in list(MATCHMAKING_QUEUE.keys()):
        if q_uid != uid:
            other_uid = q_uid
            break

    if other_uid:
        other = MATCHMAKING_QUEUE.pop(other_uid)
        if "cancel_task" in other:
            other["cancel_task"].cancel()

        try:
            await query.message.edit_text(
                "✅ <b>Opponent found! Duel starting...</b>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

        await client.send_message(
            other_uid,
            "✅ <b>Opponent found! Duel starting...</b>",
            parse_mode=ParseMode.HTML
        )

        key = _match_key(uid, other_uid)
        coin_toss = random.choice([uid, other_uid])
        batter_first = coin_toss

        if batter_first == uid:
            player_a, player_b = uid, other_uid
            name_a, name_b = name, other["name"]
        else:
            player_a, player_b = other_uid, uid
            name_a, name_b = other["name"], name

        match = {
            "player_a": player_a,
            "player_b": player_b,
            "name_a": name_a,
            "name_b": name_b,
            "phase": "a_batting",
            "a_score": 0,
            "a_balls": 0,
            "b_score": 0,
            "b_balls": 0,
            "pending_bat_choice": None,
            "pending_bowl_choice": None,
            "last_vid_a": None,
            "last_vid_b": None,
            "last_prompt_a": None,
            "last_prompt_b": None,
        }

        DUEL_MATCHES[key] = match
        USER_IN_DUEL[player_a] = key
        USER_IN_DUEL[player_b] = key

        intro = random.choice(DUEL_INTROS)
        start_text = (
            f"{intro}\n\n"
            f"➥ <b>Batting First:</b> {html.escape(name_a)}\n"
            f"➥ <b>Bowling First:</b> {html.escape(name_b)}\n\n"
            "📜 <b>Rules:</b> Pick a number. If it <b>matches</b> the opponent's — <b>OUT!</b> Otherwise batter scores their number.\n"
            "⚡ First ball in 3 seconds..."
        )

        await client.send_message(player_a, start_text, parse_mode=ParseMode.HTML)
        await client.send_message(player_b, start_text, parse_mode=ParseMode.HTML)

        await asyncio.sleep(3)
        await _send_ball_prompt(client, match)

    else:
        cancel_task = asyncio.create_task(_queue_timeout(uid, name, client))
        MATCHMAKING_QUEUE[uid] = {"name": name, "queued_at": time.time(), "cancel_task": cancel_task}

        try:
            await query.message.edit_text(
                "🔍 <b>Searching for an opponent...</b>\n"
                "⏱️ Auto-cancels in 2 minutes if no one joins.\n"
                "Share /start in your group to find opponents faster!",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
        await query.answer("You're in the queue! Searching for opponent...")


@Client.on_callback_query(filters.regex("^duel_pick:"))
async def duel_pick(client, query):
    uid = query.from_user.id
    pick = int(query.data.split(":")[1])

    if uid not in USER_IN_DUEL:
        await query.answer("You're not in a duel!", show_alert=True)
        return

    key = USER_IN_DUEL[uid]
    match = DUEL_MATCHES.get(key)
    if not match or match["phase"] == "finished":
        await query.answer("Duel already ended.", show_alert=True)
        return

    phase = match["phase"]
    if phase == "a_batting":
        batter_id, bowler_id = match["player_a"], match["player_b"]
    else:
        batter_id, bowler_id = match["player_b"], match["player_a"]

    if uid == batter_id:
        if match["pending_bat_choice"] is not None:
            await query.answer("Already picked! Waiting for bowler...", show_alert=False)
            return
        match["pending_bat_choice"] = pick
        await query.answer(f"🏏 You chose {pick}! Waiting for bowler...")
    elif uid == bowler_id:
        if match["pending_bowl_choice"] is not None:
            await query.answer("Already picked! Waiting for batter...", show_alert=False)
            return
        match["pending_bowl_choice"] = pick
        await query.answer(f" ❖ You chose {pick}! Waiting for batter...")
    else:
        await query.answer("Not your turn!", show_alert=True)
        return

    try:
        await query.message.delete()
    except Exception:
        pass

    if match["pending_bat_choice"] is not None and match["pending_bowl_choice"] is not None:
        asyncio.create_task(_process_ball(client, match))


@Client.on_message(filters.command("duel") & filters.group)
async def duel_group_cmd(client, message):
    """`/duel` is DM-only — politely redirect group users with a deep link."""
    from config import Config
    bot_username = Config.BOT_USERNAME.lstrip("@")
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "⚔️ Open duel in DM",
            url=f"https://t.me/{bot_username}?start=duel",
        )
    ]])
    await message.reply_text(
        "⚔️ <b>1v1 Duel is DM-only</b>\n"
        "──┈┄┄╌╌╌╌┄┄┈──\n"
        "Tap the button below to queue in my DM 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=buttons,
    )


@Client.on_message(filters.command("duel") & filters.private)
async def duel_private_cmd(client, message):
    text, buttons = get_duel_matchmaking_card()
    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=buttons)


async def _send_duel_log(client, match, winner_name, loser_name, winner_score, loser_score):
    try:
        from config import Config
        log_channel = getattr(Config, "LOG_CHANNEL", None)
        if not log_channel:
            return
        uid_a = match["player_a"]
        uid_b = match["player_b"]
        text = (
            "⚔️ <b>1v1 DUEL COMPLETED</b>\n"
            "──┈┄┄╌╌╌╌┄┄┈──\n"
            f"🏆 <b>Winner:</b> {html.escape(winner_name)} — {winner_score} runs\n"
            f"😔 <b>Loser:</b> {html.escape(loser_name)} — {loser_score} runs\n\n"
            f"🔢 <b>Player A ID:</b> <code>{uid_a}</code>\n"
            f"🔢 <b>Player B ID:</b> <code>{uid_b}</code>"
        )
        await asyncio.wait_for(
            client.send_message(log_channel, text, parse_mode=ParseMode.HTML),
            timeout=10,
        )
    except Exception as e:
        print(f"[Duel log bg] {e}")


def get_duel_matchmaking_card():
    text = (
        "⚔️ <b>1v1 DUEL MODE</b>\n"
        "≪━─━─━─◈─━─━─━≫\n\n"
        "🏏 Play a head-to-head duel!\n\n"
        "📜 <b>How it works:</b>\n"
        "➥ Both players pick a number each ball\n"
        "➥ Numbers match = <b>OUT!</b>\n"
        "➥ No match = batter scores their number\n"
        "➥ A bats first, then B chases\n\n"
        "⏱️ Queue timeout: <b>2 minutes</b>\n\n"
        "👇 Press <b>Ready</b> to enter matchmaking!"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Ready for Duel!", callback_data="duel_ready")]
    ])
    return text, buttons
