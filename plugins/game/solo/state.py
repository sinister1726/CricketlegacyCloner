import asyncio
import random
import time
import html
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.media_helper import send_video_or_fallback
from plugins.game.team import ACTIVE_MATCHES


COMMS = {
    1: [
        "Quick single!", "Sharp running!", "Keeps the scoreboard ticking.",
        "One run, survival mode 😌", "Strike rotated.", "Smart cricket.",
        "Pushed into the gap, one run.", "Easy single, keeps the bat ticking.",
        "Cheeky little nudge for one.", "Turned off the pads, quick single!",
    ],
    2: [
        "Placed perfectly.", "Easy two.", "Threaded the gap 🪡",
        "Smooth as butter 🧈", "Good placement.", "Running hard between the wickets!",
        "Punched to the covers, two runs.", "Driven with authority, two more.",
        "Slapped to the deep, they come back for two.", "Excellent calling, two runs!",
    ],
    3: [
        "Risky but rewarding!", "Great hustle!", "All legs, no brakes 😤",
        "Three! Brave running.", "Commitment rewarded.", "Pushed to the deep, three!",
        "They ran three! Brilliant running between the wickets!",
        "Dived in and made it — three runs!", "Three off a mistimed shot, lucky!",
        "Fields scrambling, they grabbed three!",
    ],
    4: [
        "CRACKED! 💥", "That raced away!", "FOUR! 🔥",
        "Pure timing. Chef's kiss 👨‍🍳", "To the rope!", "Boundary! No chance.",
        "Elegant drive, right to the fence 🎯", "SLAPPED through the covers — FOUR!",
        "Pulled off the front foot, that's a beauty!", "Edged and it races away — FOUR!",
        "Upper cut! Flies to the third-man fence!", "That's been creamed through mid-off!",
        "SMASHED down the ground — straight FOUR!", "Flicked off the pads, four runs!",
    ],
    5: [
        "Overthrows! Chaos! 😂", "Five runs — fielding.exe crashed 💀",
        "Bonus runs! Lucky break!", "Chaos in the field!",
        "Fumble in the deep gives them five!", "Misfield! Five on the board!",
    ],
    6: [
        "🚀 INTO ORBIT!", "MAXIMUM! 💥", "HUGE SIX! Gone for miles.",
        "That ball needs a passport! 🛰️", "BEAST MODE! 🔥",
        "WHAT A HIT! Straight into the stands!", "MONSTROUS! The crowd goes wild! 🏟️",
        "That's in another zip code! 🗺️", "Six appeal! Umpire's arm goes up!",
        "Absolutely DEMOLISHED! 💣", "HEAVED over the rope! Effortless power!",
        "SIX! Bat met ball and the ball LOST! 😤", "Picked up and launched! MAXIMUM!",
        "Skyline shot! Nowhere to be found! 🌌",
    ],
}


def _mention(match, user_id):
    name = match.get("user_cache", {}).get(user_id, "Player")
    return f"<a href='tg://user?id={user_id}'>{html.escape(name)}</a>"


def get_back_btn(chat_id):
    clean = str(chat_id).replace("-100", "")
    link = f"https://t.me/c/{clean}/999999999"
    return InlineKeyboardMarkup([[InlineKeyboardButton("Back to Group 🏏", url=link)]])


async def safe_send(coro):
    try:
        return await coro
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            return await coro
        except Exception:
            pass
    except Exception:
        pass
    return None


async def try_send_video(client, chat_id, key, caption, reply_markup=None):
    return await send_video_or_fallback(
        client, chat_id, "run", key, caption, reply_markup=reply_markup
    )


async def send_solo_ball_prompt(client, match):
    if match.get("prompt_dispatched"):
        return

    match["prompt_dispatched"] = True
    chat_id = match["chat_id"]
    bowler_id = match["current_bowler"]
    batter_id = match["current_batter"]

    if not bowler_id or not batter_id:
        match["prompt_dispatched"] = False
        return

    user_cache = match.get("user_cache", {})
    bowler_name = html.escape(user_cache.get(bowler_id, "Bowler"))
    batter_name = html.escape(user_cache.get(batter_id, "Batter"))

    if "bot_username" not in match:
        try:
            me = await client.get_me()
            match["bot_username"] = me.username
        except Exception:
            match["bot_username"] = "NexoraCricketBot"

    bot_username = match["bot_username"]
    spell_ball = match.get("balls_in_spell", 0) + 1

    group_btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("ᴅᴇʟɪᴠᴇʀ ʙᴀʟʟ ⚾", url=f"https://t.me/{bot_username}")
    ]])

    group_caption = (
        f"🏟️ <b>𝗦𝗢𝗟𝗢 𝗗𝗘𝗟𝗜𝗩𝗘𝗥𝗬</b>\n"
        f"──┈┄┄╌╌╌╌┄┄┈──\n"
        f"🎯 <a href='tg://user?id={bowler_id}'>{bowler_name}</a> is bowling to <b>{batter_name}</b>\n"
        f"🔢 Bowler, check your PM to deliver! (Ball {spell_ball}/3)"
    )

    asyncio.create_task(try_send_video(client, chat_id, "Bowling", group_caption, group_btn))

    try:
        await client.send_message(
            bowler_id,
            (
                "🏏 <b>𝗬𝗢𝗨𝗥 𝗧𝗨𝗥𝗡 𝗧𝗢 𝗕𝗢𝗪𝗟!</b>\n"
                "──┈┄┄╌╌╌╌┄┄┈──\n"
                f"👤 <b>Batter:</b> {batter_name}\n"
                "🔢 Send a number (<b>1-6</b>) to bowl.\n"
                "──┈┄┄╌╌╌╌┄┄┈──\n"
                f"🎯 <b>Spell Ball:</b> {spell_ball} / 3"
            ),
            parse_mode=ParseMode.HTML,
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await client.send_message(
                bowler_id,
                f"🏏 <b>Your turn to bowl!</b> Ball {spell_ball}/3 — Send 1-6",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            match["prompt_dispatched"] = False
            return
    except Exception as e:
        match["prompt_dispatched"] = False
        try:
            await client.send_message(
                chat_id,
                f"⚠️ Could not DM {bowler_name}. Please start the bot in PM!",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        print(f"Solo DM bowler fail: {e}")
        return

    if "timeouts" not in match:
        match["timeouts"] = {
            "bowler": {"fails": 0, "task": None},
            "batter": {"fails": 0, "task": None},
        }

    t = match["timeouts"]["bowler"]
    if t.get("task") and not t["task"].done():
        t["task"].cancel()

    from plugins.game.solo.timeouts import start_solo_timer
    match["timeouts"]["bowler"]["task"] = asyncio.create_task(
        start_solo_timer(match, "bowler")
    )


@Client.on_message(filters.private & filters.regex("^[1-6]$"), group=-2)
async def solo_bowler_dm(client, message):
    uid = message.from_user.id

    match = next(
        (
            m
            for m in list(ACTIVE_MATCHES.values())
            if m.get("mode") == "Solo"
            and m.get("current_bowler") == uid
            and m.get("phase") == "LIVE"
        ),
        None,
    )

    if not match or match.get("bowled"):
        return

    match["last_active"] = time.time()
    match["last_bowl"] = int(message.text)
    match["bowled"] = True

    t = match.get("timeouts", {}).get("bowler", {}).get("task")
    if t:
        try:
            t.cancel()
        except Exception:
            pass

    chat_id = match["chat_id"]
    back_btn = get_back_btn(chat_id)

    await safe_send(message.reply_text("⚾️", quote=True))
    await safe_send(message.reply_text(
        f"✅ <b>Ball Delivered: {message.text}</b>\nReturn to the group!",
        reply_markup=back_btn,
        parse_mode=ParseMode.HTML,
    ))

    batter_id = match["current_batter"]
    batter_name = html.escape(match.get("user_cache", {}).get(batter_id, "Batter"))
    spell_ball = match.get("balls_in_spell", 0) + 1

    group_caption = (
        f"⚾ <b>Ball Delivered!</b>  Spell Ball: {spell_ball} / 3\n"
        f"🏏 Batter <a href='tg://user?id={batter_id}'>{batter_name}</a>, "
        f"send your shot (1–6) in the group!"
    )

    asyncio.create_task(try_send_video(client, chat_id, "Batting", group_caption))

    t2 = match.get("timeouts", {}).get("batter", {}).get("task")
    if t2:
        try:
            t2.cancel()
        except Exception:
            pass

    from plugins.game.solo.timeouts import start_solo_timer
    match["timeouts"]["batter"]["task"] = asyncio.create_task(
        start_solo_timer(match, "batter")
    )


@Client.on_message(filters.group & filters.regex("^[1-6]$"), group=-2)
async def solo_batter_handler(client, message):
    uid = message.from_user.id
    chat_id = message.chat.id

    match = ACTIVE_MATCHES.get(chat_id)
    if not match:
        return

    if match.get("mode") != "Solo":
        return

    match["last_active"] = time.time()

    if (
        not match.get("bowled")
        or match.get("batted")
        or match.get("phase") != "LIVE"
    ):
        return

    if uid != match.get("current_batter"):
        return

    bat_num = int(message.text)

    if bat_num == 0:
        await safe_send(message.reply_text(
            "❌ <b>0 (dot) not allowed in Solo mode!</b> Play a shot (1-6).",
            parse_mode=ParseMode.HTML,
            quote=True,
        ))
        return

    match["batted"] = True

    await safe_send(message.reply_text("👍", quote=True))

    bowl_num = match.get("last_bowl")

    t = match.get("timeouts", {}).get("batter", {}).get("task")
    if t:
        try:
            t.cancel()
        except Exception:
            pass

    from plugins.game.solo.engine import solo_advance_ball

    is_out = bat_num == bowl_num

    if is_out:
        bowler_id = match["current_bowler"]
        mention_batter = _mention(match, uid)
        mention_bowler = _mention(match, bowler_id)
        caption = (
            f"☝️ <b>OUT!</b>\n\n"
            f"👤 {mention_batter} is dismissed!\n"
            f"🎯 {mention_bowler} strikes! 🔥"
        )
        await try_send_video(client, chat_id, "Out", caption)
        await solo_advance_ball(match, "W")
    else:
        runs = bat_num
        comm = random.choice(COMMS.get(runs, ["Nice shot!"]))
        caption = f"🏏 <b>{runs} Run(s)!</b>\n╰⊚ {comm}"
        await try_send_video(client, chat_id, str(runs), caption)
        await solo_advance_ball(match, runs)
