import asyncio
import random
import time
import html
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.enums import ParseMode

from Assets.files import RUN_VIDEOS
from plugins.game.team import ACTIVE_MATCHES
from plugins.game.team.over_engine import advance_ball
from plugins.game.team.timeouts import start_timer

GROUP_COOLDOWN = {}

def get_back_to_group_markup(group_chat_id: int):
    clean_chat_id = str(group_chat_id).replace("-100", "")
    group_link = f"https://t.me/c/{clean_chat_id}/999999999"
    return InlineKeyboardMarkup([[InlineKeyboardButton("Back to Group 🏏", url=group_link)]])

def get_mention(match, user_id):
    name = match.get("user_cache", {}).get(user_id, "Player")
    safe_name = html.escape(name) 
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'
    
async def try_send_video(client, chat_id, key, caption, reply_markup=None):
    video_list = RUN_VIDEOS.get(str(key), [])
    if not video_list:
        return await client.send_message(chat_id, caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    file_id = random.choice(video_list)
    if not file_id or file_id.startswith("FILE_ID"):
        return await client.send_message(chat_id, caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    try:
        return await client.send_video(
            chat_id=chat_id,
            video=file_id,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        err = str(e).upper()
        if "ANIMATION" in err or "CONTENT_TYPE" in err or "VIDEO_CONTENT_REQUIRED" in err:
            try:
                return await client.send_animation(
                    chat_id=chat_id,
                    animation=file_id,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            except Exception as anim_e:
                print(f"❌ Both media types failed: {anim_e}")

        return await client.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def send_result_visuals(client, chat_id, key, caption):
    await try_send_video(client, chat_id, key, caption)

def get_display_ball_no(match):
    balls_bowled = len(match.get("current_over_balls", []))
    return min(balls_bowled + 1, 6)


async def start_first_ball(client, match):
    is_new_over = len(match.get("current_over_balls", [])) == 0
    if match.get("prompt_dispatched") and not is_new_over:
        return
        
    match["prompt_dispatched"] = True
    
    if client is None:
        client = match.get("client")

    if client is None:
        match["prompt_dispatched"] = False
        print(f"❌ Critical: Client missing for Match {match.get('game_id')}")
        return

    chat_id = match.get("chat_id")
    bowler_id = match.get("current_bowler")
    striker_id = match.get("striker")
    
    if not chat_id or not bowler_id:
        match["prompt_dispatched"] = False
        return

    players = match.get("players", {})
    bat_team_key = match.get("batting_team")
    bat_team = match.get("teams", {}).get(bat_team_key, {})
    team_players = bat_team.get("players", [])

    def is_alive(uid):
        return uid and uid in team_players and not players.get(uid, {}).get("is_out", False)

    if not is_alive(striker_id):
        alive = [u for u in team_players if is_alive(u)]
        match["striker"] = alive[0] if alive else None
        striker_id = match["striker"]

    if not is_alive(match.get("non_striker")):
        remaining = [u for u in team_players if is_alive(u) and u != striker_id]
        match["non_striker"] = remaining[0] if remaining else None

    if not striker_id:
        match["prompt_dispatched"] = False
        return

    if "bot_username" not in match:
        try:
            me = await client.get_me()
            match["bot_username"] = me.username
        except Exception:
            match["bot_username"] = "NexoraCricketBot"

    bot_username = match["bot_username"]

    if "timeouts" not in match:
        match["timeouts"] = {
            "bowler": {"fails": 0, "task": None},
            "batter": {"fails": 0, "task": None},
        }

    user_cache = match.get("user_cache", {})
    
    raw_bowler_name = user_cache.get(bowler_id, "Bowler")
    raw_striker_name = user_cache.get(striker_id, "Batter")
    
    bowler_name = html.escape(raw_bowler_name)
    striker_name = html.escape(raw_striker_name)

    group_btn = InlineKeyboardMarkup([[ 
        InlineKeyboardButton("ᴅᴇʟɪᴠᴇʀ ʙᴀʟʟ ⚾", url=f"https://t.me/{bot_username}")
    ]])

    bowler_mention = f"<a href='tg://user?id={bowler_id}'>{bowler_name}</a>"
    caption = (
        f"🏟️ 𝗡𝗘𝗫𝗧 𝗗𝗘𝗟𝗜𝗩𝗘𝗥𝗬\n"
        f"──┈┄┄╌╌╌╌┄┄┈──\n"
        f"🎯 {bowler_mention} ɪꜱ ʙᴏᴡʟɪɴɢ ᴛᴏ <b>{striker_name}</b>\n"
        f"🔢 Bowler, check your PM to deliver!"
    )

    try:
        await try_send_video(client, chat_id, "Bowling", caption, group_btn)
    except Exception as e:
        print(f"Group Notify Error: {e}")

        try:
            await client.send_message(chat_id, caption, reply_markup=group_btn, parse_mode=ParseMode.HTML)
        except:
            pass

    ball_no = get_display_ball_no(match)

    try:
        await client.send_message(
            bowler_id,
            (
                "🏏𝗬𝗢𝗨𝗥 𝗧𝗨𝗥𝗡 𝗧𝗢 𝗕𝗢𝗪𝗟!\n"
                "──┈┄┄╌╌╌╌┄┄┈──\n"
                f"👤 <b>Batter:</b> {striker_name}\n"
                "🔢 Send a number (<b>1-6</b>) to bowl.\n"
                "──┈┄┄╌╌╌╌┄┄┈──\n"
                f"🎯 <b>Over Ball :</b> {ball_no} / 6"
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        match["prompt_dispatched"] = False
        try:
            await client.send_message(chat_id, f"⚠️ <b>Error:</b> Could not DM {bowler_name}. Please start the bot in PM!", parse_mode=ParseMode.HTML)
        except:
            pass
        print(f"⚠️ DM Fail: {e}")
        return

    t_data = match["timeouts"]["bowler"]
    if t_data.get("task") and not t_data["task"].done():
        t_data["task"].cancel()

    match["timeouts"]["bowler"]["task"] = asyncio.create_task(
        start_timer(match, "bowler")
    )


@Client.on_message(filters.private & filters.regex("^[1-6]$"), group=-1)
async def bowler_dm_handler(client, message):
    uid = message.from_user.id

    match = next(
        (m for m in list(ACTIVE_MATCHES.values()) if m.get("current_bowler") == uid),
        None
    )

    if not match or match.get("phase") != "LIVE" or match.get("bowled"):
        return

    match["last_active"] = time.time()
    match["last_bowl"] = int(message.text)
    match["bowled"] = True

    if "timeouts" not in match:
        match["timeouts"] = {
            "bowler": {"fails": 0, "task": None},
            "batter": {"fails": 0, "task": None},
        }

    t_bowler = match["timeouts"]["bowler"]
    if t_bowler.get("task"):
        try:
            t_bowler["task"].cancel()
        except Exception:
            pass

    chat_id = match["chat_id"]
    
    back_btn = get_back_to_group_markup(chat_id)

    await message.reply_text("⚾️", quote=True)

    asyncio.create_task(
        message.reply_text(
            f"✅ <b>Ball Delivered:</b> <b>{message.text}</b>\n\n"
            "Return to the group to watch the outcome unfold!",
            reply_markup=back_btn,
            parse_mode=ParseMode.HTML
        )
    )

    striker_id = match.get("striker")
    
    raw_striker_name = match.get("user_cache", {}).get(striker_id, "Batter")
    striker_name = html.escape(raw_striker_name)

    ball_no = get_display_ball_no(match)

    caption = (
        f"⚾ <b>Ball Delivered!</b>  <b>Over Ball:</b> {ball_no} / 6\n"
        f"🏏 Batter <a href='tg://user?id={striker_id}'>{striker_name}</a>, "
        f"send your shot (0–6) in the group!"
    )

    asyncio.create_task(
        try_send_video(client, chat_id, "Batting", caption)
    )

    t_batter = match["timeouts"]["batter"]
    if t_batter.get("task"):
        try:
            t_batter["task"].cancel()
        except Exception:
            pass

    match["timeouts"]["batter"]["task"] = asyncio.create_task(
        start_timer(match, "batter")
    )
    
@Client.on_message(filters.group & filters.regex("^[0-6]$"), group=-1)
async def batter_handler(client, message):
    uid = message.from_user.id
    chat_id = message.chat.id

    match = ACTIVE_MATCHES.get(chat_id)
    if match:
        match["last_active"] = time.time()

    if (
        not match
        or not match.get("bowled")
        or match.get("batted")
        or match.get("phase") != "LIVE"
    ):
        return

    if uid != match.get("striker"):
        return

    bat_num = int(message.text)

    over_balls = match.get("current_over_balls", [])

    is_hat_trick_ball = (
        len(over_balls) >= 2
        and over_balls[-1] == "W"
        and over_balls[-2] == "W"
    )

    if is_hat_trick_ball and bat_num == 0:
        await message.reply_text(
            "🧢 <b>Hat-trick ball!</b>\n"
            "❌ Dot (0) not allowed\n"
            "💥 Play a shot!",
            parse_mode=ParseMode.HTML,
            quote=True
        )
        return
 
    match["batted"] = True

    await message.reply_text("👍", quote=True)

    bowl_num = match.get("last_bowl")
    bowler_id = match.get("current_bowler")

    t = match.get("timeouts", {}).get("batter", {}).get("task")
    if t:
        try:
            t.cancel()
        except:
            pass

    is_out = (bat_num == bowl_num)
    runs = 0 if bat_num == 0 else bat_num

    if is_out:
        mention = get_mention(match, uid)
        bowler_mention = get_mention(match, bowler_id)

        caption = (
            f"☝️ <b>OUT!</b>\n\n"
            f"👤 {mention} dismissed!\n"
            f"🎯 {bowler_mention} is on fire 🔥"
        )

        await try_send_video(client, chat_id, "Out", caption)
        await advance_ball(match, "W")

    else:
        comms_list = {
            0: ["Dead bat. Crowd boos 😴", "Stonewall defence.", "Dot ball pressure builds…", "Bat says no, runs say bye 👋", "That ball died a lonely death.", "Even the bowler looks bored.", "Dot ball sponsored by patience.", "Defense so solid, WiFi can’t pass through.", "Crowd checks phone. Nothing happened.", "Pure defence, zero entertainment.", "A dot so quiet you can hear regrets.", "Commentator running out of words.", "Batting like it’s a test match 😐", "Kya hi ukhaad liya? Dot ball.", "Yeh shot nahi tha, majboori thi.", "Bowler smiling for no reason.", "Fielders relax, nothing to do.", "That ball deserves a refund.", "Momentum paused. Completely.", "Silence louder than crowd noise.", "Solid defensive technique on display.", "Good line respected by the batter.", "No scoring opportunity created.", "Bowler wins that mini battle.", "Textbook block.", "Correct shot for the situation.", "Scoreboard unchanged. Ego unchanged.", "That was cricket ASMR.", "Ball met bat. Nothing else happened.", "This over needs caffeine."],
            1: ["Quick single!", "Sharp running!", "Keeps the scoreboard ticking.", "Steal of the century 🏃‍♂️", "Blink and you miss it!", "Just enough to survive.", "One run, infinite relief 😌", "Bowler annoyed, batter satisfied.", "Chori pakdi gayi, par run mil gaya 😏", "Fitness check passed.", "Ek run bhi aaj kal mehenga hai!", "Risk liya… bach gaye!", "Soft hands, smart feet.", "Sneaky but effective.", "Bowler not impressed.", "Captain sighs in disappointment.", "Hard-earned single.", "Minimal risk, maximum sense.", "Strike rotated successfully.", "Game awareness on point.", "One run and a long breath.", "Not pretty, but it works.", "Survival mode activated.", "Good placement into the gap.", "Rotates strike nicely.", "Keeps pressure manageable."],
            2: ["Placed perfectly.", "Good awareness!", "Easy two.", "Threaded the gap like a needle 🪡", "Lazy fielding punished.", "They’ll take that all day.", "Smooth as butter 🧈", "Running between wickets: 10/10.", "Do run, no tension.", "Gap mila, mauka mila!", "Fielders still loading…", "Placement coaching DVD mein jayega.", "Timing beats power.", "Comfortable running.", "Good communication between batters.", "Bowler not happy.", "Safe cricket, smart cricket.", "Two runs without fuss.", "Pressure released slightly.", "Ground fielding exposed.", "Fielding standards questioned.", "That gap was illegal.", "Excellent shot selection.", "Perfect use of the field."],
            3: ["Risky but rewarding!", "Great hustle!", "All legs, no brakes 😤", "Fielders confused, batters amused.", "That needed commitment — and lungs!", "Calculated madness!", "Captain screaming, crowd screaming louder.", "Teen run ya heart attack!", "Galti ki gunjaish zero thi 😬", "Yeh running nahi, sprint thi!", "Stadium mein oxygen kam pad gayi.", "Close call but worth it.", "Pressure cricket at its finest.", "Fielding chaos unlocked.", "Bowler furious.", "Crowd loves the drama.", "Risk meter full.", "Pure adrenaline.", "That was brave.", "Almost disaster!", "One bad throw and it was over.", "Bowler aged 5 years.", "Excellent commitment between wickets.", "High-risk, high-reward running."],
            4: ["CRACKED! 💥", "That raced away!", "Boundary finds the rope!", "Pure timing. Chef’s kiss 👨‍🍳💋", "Bowler tried. Ball didn’t listen.", "Placed where the fielder isn’t.", "That’s a textbook boundary!", "Sponsors very happy right now.", "Chaar run aur bowler pareshaan!", "Shot mein class, bowler mein sass.", "Yeh ground shot ke liye chhota pad gaya!", "Ball bole: bas karo bhai!", "Elegant stroke play.", "No chance for anyone.", "Crowd on its feet!", "That was effortless.", "Boundary like a statement.", "Timing > power.", "Bowler loses length.", "Confidence booster!", "Bowler absolutely cooked.", "That gap was personal.", "Exquisite timing and placement.", "Classic cricketing shot."],
            5: ["Chaos in the field!", "Overthrows galore!", "Fielding.exe has stopped working 💀", "Everyone running, nobody stopping!", "Bowler questioning life choices.", "Captain hiding behind the cap.", "This is comedy cricket 🤡", "Yeh fielding nahi, blooper reel hai!", "Ball bhi confused, fielder bhi!", "Coach ne aankhein band kar li 👀", "Five runs… aur izzat free mein!", "Absolute panic stations.", "Pressure causes mistakes.", "Fielding meltdown.", "Communication? Missing.", "One error, big damage.", "Bowler helpless.", "Crowd laughing hard.", "Chaos unlocked.", "Defensive drills incoming.", "That was illegal fielding.", "Someone getting benched.", "Capitalized on fielding errors.", "Awareness to keep running."],
            6: ["🚀 INTO ORBIT!", "HUGE MAXIMUM!", "Bowler in shambles 😭", "That ball needs a passport!", "Satellite launched successfully 🛰️", "Clean hit, cleaner vibes 🔥", "Crowd loses its mind!", "Somewhere a fielder just gave up.", "Six runs and emotional damage 💔", "Yeh shot nahi, warning thi!", "Ball milne ka koi chance nahi!", "Bowler bole: bas bhai, over khatam karo!", "Stadium ke bahar giri hai yeh!", "SHOT ITNI BADI, SCOREBOARD HIL GAYA 💣", "Absolutely smoked!", "That’s gone miles.", "Pure power!", "No doubts, no drama.", "Bowler looks at the sky.", "Momentum completely flipped.", "Bowler needs therapy.", "That landed in another district.", "Perfect swing, perfect connection.", "Clean striking at its best."]
        }

        caption = (
            f"🏏 <b>{runs} Run(s)!</b>\n"
            f"╰⊚ {random.choice(comms_list[runs])}"
        )

        await try_send_video(client, chat_id, str(runs), caption)
        await advance_ball(match, runs)

@Client.on_message(filters.command(["score", "userinfo", "graph"]) & filters.group, group=-1)
async def check_cooldown(client, message):
    chat_id = message.chat.id
    now = time.time()
    if chat_id in GROUP_COOLDOWN:
        diff = now - GROUP_COOLDOWN[chat_id]
        if diff < 10:
            await message.reply_text(f"⏳ **Slow down!** Try again after {int(10 - diff)}s.")
            await message.stop_propagation()
    GROUP_COOLDOWN[chat_id] = now
    
