import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified

from plugins.game.team import ACTIVE_MATCHES
from Assets.files import SOLO_MODE_IMAGE

async def auto_start_timer(client, chat_id):
    await asyncio.sleep(120) 
    
    match = ACTIVE_MATCHES.get(chat_id)
    if not match or match.get("mode") != "Solo" or match.get("phase") != "REGISTRATION":
        return

    if len(match["players"]) < 3:
        ACTIVE_MATCHES.pop(chat_id, None)
        await client.send_message(chat_id, "❌ <b>Solo Match Cancelled!</b>\nMinimum 3 players are required to start.", parse_mode=ParseMode.HTML)
        return

    match["phase"] = "LIVE"
    match["last_activity"] = time.time()
    
    match["striker"] = match["batting_order"][0]
    match["current_bowler"] = match["batting_order"][1] if match["batting_order"][1] != match["striker"] else match["batting_order"][2]
    match["current_batter_idx"] = 0
    match["bowler_balls"] = 0

    await client.send_message(chat_id, "🚀 <b>𝗦𝗢𝗟𝗢 𝗠𝗔𝗧𝗖𝗛 𝗦𝗧𝗔𝗥𝗧𝗘𝗗!</b>\n\nGet ready for the ultimate showdown!", parse_mode=ParseMode.HTML)

    player_list_text = "📋 <b>𝗙𝗜𝗡𝗔𝗟 𝗣𝗟𝗔𝗬𝗘𝗥 𝗟𝗜𝗦𝗧 (Turn Order)</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for idx, uid in enumerate(match["batting_order"], start=1):
        name = match["user_cache"].get(uid, "Player")
        player_list_text += f"<b>{idx}.</b> <a href='tg://user?id={uid}'>{name}</a>\n"
    
    await client.send_message(chat_id, player_list_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    await asyncio.sleep(2)
    
    await announce_solo_turn(client, chat_id, match)

async def handle_solo_timeout(client, chat_id, match, role, user_id):
    if match.get("phase") != "LIVE": return
    match["last_activity"] = time.time()
    
    mention = f"<a href='tg://user?id={user_id}'>{match['user_cache'].get(user_id, 'Player')}</a>"
    match["players"][user_id]["runs"] -= 6

    msg = f"🚫 <b>CLOCK WINS (60s Timeout)</b>\n\n{mention} couldn't beat the timer ⏰\nPunished with <b>-6 runs</b>.\n"
    
    if role == "batter":
        msg += "☝️ <b>Batter is OUT!</b>"
        await client.send_message(chat_id, msg, parse_mode=ParseMode.HTML)
        await rotate_solo_players(client, chat_id, match, is_wicket=True)
    else:
        msg += "🎳 <b>Bowler removed from attack!</b>"
        match["bowler_balls"] = 3 
        await client.send_message(chat_id, msg, parse_mode=ParseMode.HTML)
        await rotate_solo_players(client, chat_id, match, is_wicket=False)

async def start_turn_timer(client, chat_id, match, role, user_id):
    await asyncio.sleep(60)
    
    current_match = ACTIVE_MATCHES.get(chat_id)
    if not current_match or current_match.get("phase") != "LIVE": return
    
    if role == "bowler" and current_match.get("bowler_input") is not None: return
    if role == "batter" and current_match.get("bowler_input") is None: return
    
    await handle_solo_timeout(client, chat_id, current_match, role, user_id)

@Client.on_callback_query(filters.regex("^mode_solo$"))
async def init_solo_mode(client, query):
    chat_id = query.message.chat.id
    user = query.from_user

    ACTIVE_MATCHES[chat_id] = {
        "mode": "Solo",
        "phase": "REGISTRATION",
        "host_id": user.id,
        "players": {}, 
        "batting_order": [],
        "user_cache": {user.id: user.first_name},
        "chat_id": chat_id,
        "client": client,
        "striker": None,
        "current_bowler": None,
        "bowler_balls": 0,
        "bowler_input": None,
        "timer_task": None,
        "last_activity": time.time(),
        "lobby_msg": None 
    }

    ACTIVE_MATCHES[chat_id]["players"][user.id] = {
        "runs": 0, "wickets": 0, "balls_faced": 0, "balls_bowled": 0, "is_out": False
    }
    ACTIVE_MATCHES[chat_id]["batting_order"].append(user.id)

    asyncio.create_task(auto_start_timer(client, chat_id))

    await query.answer("Solo Mode Lobby Created! 🏏")
    try:
        msg = await query.message.edit_media(
            media=InputMediaPhoto(
                media=SOLO_MODE_IMAGE, 
                caption="👤 <b>𝗦𝗢𝗟𝗢 𝗠𝗢𝗗𝗘 — 𝗥𝗘𝗚𝗜𝗦𝗧𝗥𝗔𝗧𝗜𝗢𝗡</b>\n\n🔥 <b>Rules:</b>\n• Play via DM and Group.\n• Type <code>/join</code> to enter.\n• Type <code>/leave</code> to exit.\n• 120s automatic start!\n\n👥 <b>Joined:</b> 1\n⏳ <b>Starting in 120 seconds...</b>"
            )
        )
        ACTIVE_MATCHES[chat_id]["lobby_msg"] = msg
    except MessageNotModified: pass

@Client.on_message(filters.command("join") & filters.group)
async def join_solo_cmd(client, message):
    if not getattr(message, "from_user", None): return 
    
    chat_id = message.chat.id
    user = message.from_user
    match = ACTIVE_MATCHES.get(chat_id)

    if not match or match.get("phase") != "REGISTRATION" or match.get("mode") != "Solo": return 
    if user.id in match["players"]:
        return await message.reply_text("You are already in the match!", quote=True)

    match["players"][user.id] = {"runs": 0, "wickets": 0, "balls_faced": 0, "balls_bowled": 0, "is_out": False}
    match["batting_order"].append(user.id)
    match["user_cache"][user.id] = user.first_name
    match["last_activity"] = time.time()
    
    total_players = len(match["players"])
    await message.reply_text(f"✅ Joined at Position #{total_players}!", quote=True)
    await update_lobby(match, total_players)

@Client.on_message(filters.command("leave") & filters.group)
async def leave_solo_cmd(client, message):
    if not getattr(message, "from_user", None): return 
    
    chat_id = message.chat.id
    user = message.from_user
    match = ACTIVE_MATCHES.get(chat_id)

    if not match or match.get("phase") != "REGISTRATION" or match.get("mode") != "Solo": return 
    if user.id not in match["players"]:
        return await message.reply_text("You are not in the match!", quote=True)

    del match["players"][user.id]
    match["batting_order"].remove(user.id)
    match["last_activity"] = time.time()
    
    await message.reply_text("👋 You have left the match!", quote=True)
    await update_lobby(match, len(match["players"]))

async def update_lobby(match, total_players):
    if not match.get("lobby_msg"): return
    try:
        await match["lobby_msg"].edit_caption(
            caption=f"👤 <b>𝗦𝗢𝗟𝗢 𝗠𝗢𝗗𝗘 — 𝗥𝗘𝗚𝗜𝗦𝗧𝗥𝗔𝗧𝗜𝗢𝗡</b>\n\n🔥 <b>Rules:</b>\n• Play via DM and Group.\n• Type <code>/join</code> to enter.\n• Type <code>/leave</code> to exit.\n• 120s automatic start!\n\n👥 <b>Joined:</b> {total_players}\n⏳ <b>Starting automatically...</b>",
            parse_mode=ParseMode.HTML
        )
    except MessageNotModified: pass

@Client.on_message(filters.command("members") & filters.group)
async def solo_members_cmd(client, message):
    if not getattr(message, "from_user", None): return
    chat_id = message.chat.id
    match = ACTIVE_MATCHES.get(chat_id)

    if not match or match.get("mode") != "Solo": return 

    text = "📋 <b>𝗦𝗢𝗟𝗢 𝗠𝗔𝗧𝗖𝗛 𝗣𝗟𝗔𝗬𝗘𝗥𝗦 (Join Order)</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for idx, uid in enumerate(match["batting_order"], start=1):
        name = match["user_cache"].get(uid, "Player")
        status = " (Out)" if match["players"][uid].get("is_out") else ""
        text += f"<b>{idx}.</b> <a href='tg://user?id={uid}'>{name}</a>{status}\n"

    await message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def announce_solo_turn(client, chat_id, match):
    batter_name = match["user_cache"][match["striker"]]
    bowler_name = match["user_cache"][match["current_bowler"]]
    match["bowler_input"] = None
    match["last_activity"] = time.time()
    
    if match.get("timer_task"): match["timer_task"].cancel()
    
    ball_no = match["bowler_balls"] + 1 
    bot = await client.get_me()
    
    await client.send_message(
        chat_id,
        f"🏏 <b>Game On!</b> (Ball {ball_no}/3)\n\n"
        f"🤺 <b>Batsman:</b> <a href='tg://user?id={match['striker']}'>{batter_name}</a> (Play here in Group)\n"
        f"🎳 <b>Bowler:</b> <a href='tg://user?id={match['current_bowler']}'>{bowler_name}</a> (Play in Bot DM)\n\n"
        f"🚨 <b>Bowler</b>, check your DM or click here: @{bot.username}\n⏳ <i>60s Timer Started!</i>",
        parse_mode=ParseMode.HTML
    )

    try:
        await client.send_message(
            match["current_bowler"],
            f"🏏 <b>YOUR TURN TO BOWL!</b>\n\n🤺 <b>Batter:</b> {batter_name}\n⚾ <b>Ball Number:</b> {ball_no}/3\n\n👉 Send a number between <b>1 to 6</b> here to bowl.\n⏳ <i>You have 60 seconds!</i>"
        )
    except Exception:
        await client.send_message(chat_id, f"⚠️ <a href='tg://user?id={match['current_bowler']}'>{bowler_name}</a>, please Start the bot in DM to bowl!", parse_mode=ParseMode.HTML)

    match["timer_task"] = asyncio.create_task(start_turn_timer(client, chat_id, match, "bowler", match["current_bowler"]))

async def rotate_solo_players(client, chat_id, match, is_wicket=False):
    players = match["batting_order"]
    match["last_activity"] = time.time()
    
    if is_wicket:
        match["players"][match["striker"]]["is_out"] = True
        match["current_batter_idx"] += 1
        
        if match["current_batter_idx"] >= len(players):
            return await end_solo_match(match)
            
        match["striker"] = players[match["current_batter_idx"]]
        match["bowler_balls"] = 0 
        
    else:
        match["bowler_balls"] += 1

    if match["bowler_balls"] >= 3:
        await client.send_message(chat_id, "🔄 <b>Bowler Changed! (3 Balls Completed)</b>", parse_mode=ParseMode.HTML)
        match["bowler_balls"] = 0
        
        curr_b_idx = players.index(match["current_bowler"])
        for _ in range(len(players)):
            curr_b_idx = (curr_b_idx + 1) % len(players)
            if players[curr_b_idx] != match["striker"] and not match["players"][players[curr_b_idx]]["is_out"]:
                match["current_bowler"] = players[curr_b_idx]
                break

    await announce_solo_turn(client, chat_id, match)

@Client.on_message(filters.private & filters.text)
async def solo_dm_bowler(client, message):
    if not getattr(message, "from_user", None): return 
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    if not text.isdigit(): return
    number = int(text)
    if number < 1 or number > 6: return 
    
    active_match = None
    for cid, m in ACTIVE_MATCHES.items():
        if m.get("mode") == "Solo" and m.get("phase") == "LIVE" and m.get("current_bowler") == user_id:
            active_match = m
            break
            
    if not active_match: return 
    if active_match["bowler_input"] is not None:
        return await message.reply_text("⚠️ You have already bowled! Wait for the batter.")
        
    if active_match.get("timer_task"): active_match["timer_task"].cancel()
        
    active_match["bowler_input"] = number
    active_match["last_activity"] = time.time()
    ball_no = active_match["bowler_balls"] + 1
    striker_name = active_match["user_cache"].get(active_match["striker"], "Batter")
    
    await message.reply_text(f"✅ You bowled **{number}** for Ball {ball_no}/3 to {striker_name}! Watch the group.")
    
    chat_id = active_match["chat_id"]
    await client.send_message(
        chat_id,
        f"🎯 <b>Bowler has bowled Ball {ball_no}/3 from DM!</b>\n<a href='tg://user?id={active_match['striker']}'>{striker_name}</a>, it's your turn! Send your hit (1-6) here.\n⏳ <i>60s Timer Started!</i>",
        parse_mode=ParseMode.HTML
    )
    
    active_match["timer_task"] = asyncio.create_task(start_turn_timer(client, chat_id, active_match, "batter", active_match["striker"]))

@Client.on_message(filters.group & filters.text)
async def solo_group_batter(client, message):
    if not getattr(message, "from_user", None): return 
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()

    match = ACTIVE_MATCHES.get(chat_id)
    if not match or match.get("mode") != "Solo" or match.get("phase") != "LIVE": return

    if not text.isdigit(): return
    number = int(text)
    
    if number == 0:
        return await message.reply_text("⚠️ 0 (Defend) is disabled in Solo Mode!", parse_mode=ParseMode.HTML)
    if number < 1 or number > 6: return 

    striker, bowler = match.get("striker"), match.get("current_bowler")
    if user_id != striker: return 
        
    if match.get("bowler_input") is None:
        return await message.reply_text("⚠️ Wait for the bowler to bowl in DM first!")
        
    if match.get("timer_task"): match["timer_task"].cancel()
        
    batter_input = number
    bowler_input = match.pop("bowler_input")
    match["last_activity"] = time.time()
    
    striker_name = match['user_cache'].get(striker, 'Batter')
    bowler_name = match['user_cache'].get(bowler, 'Bowler')
    ball_no = match["bowler_balls"] + 1
    
    if batter_input == bowler_input:
        msg = f"☝️ <b>WICKET! CLEAN BOWLED!</b> (Ball {ball_no}/3)\n\n🎳 <a href='tg://user?id={bowler}'>{bowler_name}</a> picked {bowler_input}\n🏏 <a href='tg://user?id={striker}'>{striker_name}</a> picked {batter_input}\n\n<i>Eliminated!</i>"
        try:
            await client.send_message(chat_id, msg, parse_mode=ParseMode.HTML)
        except: pass
            
        match["players"][bowler]["wickets"] += 1
        match["players"][striker]["balls_faced"] += 1
        match["players"][bowler]["balls_bowled"] += 1
        await rotate_solo_players(client, chat_id, match, is_wicket=True)
        
    else:
        header = "🚀 <b>SIX RUNS!</b>" if batter_input == 6 else "🔥 <b>FOUR RUNS!</b>" if batter_input == 4 else f"🏃 <b>{batter_input} RUNS!</b>"
        msg = f"{header} (Ball {ball_no}/3)\n\n🏏 <a href='tg://user?id={striker}'>{striker_name}</a> picked {batter_input}\n🎳 Bowler picked {bowler_input}"
        
        try:
            await client.send_message(chat_id, msg, parse_mode=ParseMode.HTML)
        except: pass
            
        match["players"][striker]["runs"] += batter_input
        match["players"][striker]["balls_faced"] += 1
        match["players"][bowler]["balls_bowled"] += 1
        await rotate_solo_players(client, chat_id, match, is_wicket=False)

@Client.on_message(filters.command("score") & filters.group)
async def solo_score_cmd(client, message):
    if not getattr(message, "from_user", None): return
    chat_id = message.chat.id
    match = ACTIVE_MATCHES.get(chat_id)

    if not match or match.get("mode") != "Solo" or match.get("phase") != "LIVE": return 

    res_text = "📊 <b>𝗦𝗢𝗟𝗢 𝗠𝗔𝗧𝗖𝗛 - 𝗟𝗜𝗩𝗘 𝗦𝗖𝗢𝗥𝗘</b> 📊\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for uid in match["batting_order"]:
        stats = match["players"][uid]
        name = match["user_cache"].get(uid, "Player")
        status = "❌ Out" if stats["is_out"] else "✅ Not Out"
        res_text += f"👤 <b>{name}</b>: {stats['runs']}R ({stats['balls_faced']}b) | {stats['wickets']}W | {status}\n"

    await message.reply_text(res_text, parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("end") & filters.group)
async def solo_end_cmd(client, message):
    if not getattr(message, "from_user", None): return
    chat_id = message.chat.id
    match = ACTIVE_MATCHES.get(chat_id)

    if not match or match.get("mode") != "Solo": return
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, End Match", callback_data="confirm_end_solo")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_end_solo")]
    ])
    
    await message.reply_text("⚠️ <b>Are you sure you want to end the current match?</b>", reply_markup=buttons, parse_mode=ParseMode.HTML)

@Client.on_callback_query(filters.regex("^confirm_end_solo$"))
async def confirm_end_solo(client, query):
    chat_id = query.message.chat.id
    match = ACTIVE_MATCHES.get(chat_id)
    
    if not match or match.get("mode") != "Solo":
        return await query.message.delete()
        
    if query.from_user.id != match.get("host_id"):
        return await query.answer("Only the match host can end the match!", show_alert=True)
        
    await query.message.edit_text("🛑 <b>Match ended early by Host!</b>", parse_mode=ParseMode.HTML)
    await end_solo_match(match)

@Client.on_callback_query(filters.regex("^cancel_end_solo$"))
async def cancel_end_solo(client, query):
    chat_id = query.message.chat.id
    match = ACTIVE_MATCHES.get(chat_id)
    
    if not match or match.get("mode") != "Solo":
        return await query.message.delete()
        
    if query.from_user.id != match.get("host_id"):
        return await query.answer("Only the match host can cancel this!", show_alert=True)
        
    await query.message.delete()

async def end_solo_match(match):
    client, chat_id = match["client"], match["chat_id"]
    players = match["players"]

    if match.get("timer_task"): match["timer_task"].cancel()

    if not players:
        ACTIVE_MATCHES.pop(chat_id, None)
        return

    top_batsman_id = max(players, key=lambda k: players[k]["runs"])
    top_bowler_id = max(players, key=lambda k: players[k]["wickets"])

    def get_name(uid): return match["user_cache"].get(uid, "Player")

    res_text = "🏁 <b>𝗦𝗢𝗟𝗢 𝗠𝗔𝗧𝗖𝗛 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗</b> 🏁\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    res_text += f"🥇 <b>Best Batsman:</b> <a href='tg://user?id={top_batsman_id}'>{get_name(top_batsman_id)}</a> ➞ <b>{players[top_batsman_id]['runs']} Runs</b>\n"
    res_text += f"🎯 <b>Best Bowler:</b> <a href='tg://user?id={top_bowler_id}'>{get_name(top_bowler_id)}</a> ➞ <b>{players[top_bowler_id]['wickets']} Wickets</b>\n\n"
    
    res_text += "📊 <b>𝗙𝗨𝗟𝗟 𝗦𝗖𝗢𝗥𝗘𝗕𝗢𝗔𝗥𝗗:</b>\n"
    for uid in match["batting_order"]:
        stats = players[uid]
        status = "❌ Out" if stats["is_out"] else "✅ Not Out"
        res_text += f"👤 <b>{get_name(uid)}</b>: {stats['runs']}R ({stats['balls_faced']}b) | {stats['wickets']}W | {status}\n"

    await client.send_message(chat_id, res_text, parse_mode=ParseMode.HTML)
    ACTIVE_MATCHES.pop(chat_id, None)
    
