# ───────────── STANDARD LIBS ─────────────
import asyncio
import time
import os
import io
from datetime import datetime
from pyrogram.errors import ChatAdminRequired


# ───────────── PYROGRAM ─────────────
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ───────────── IMAGE / PIL ─────────────
from PIL import Image, ImageDraw, ImageFont

# ───────────── GAME STATE / INIT ─────────────
from plugins.game.team.init import ACTIVE_MATCHES
from plugins.game.team.state import GROUP_COOLDOWN

# ───────────── DATABASE ─────────────
from database.connection import db
from database.games import (
    get_active_game,
    set_phase,
    get_phase,
    user_in_other_game,
    get_team_players,
    get_shift_count,
    increment_shift,
)

# ───────────── ASSETS ─────────────
from Assets.files import MEMBERS_IMAGE

# ───────────── UTILS ─────────────
from utils.permissions import host_only
from utils.cooldown import allow

# Settings
MEMBERS_THUMB = "Assets/members.jpeg"
NAME_FONT = "Assets/namefont.ttf"

# --- SUPERFAST CACHING ---
MEMBERS_THUMB_COUNTER = {}  # chat_id -> count
AVATAR_CACHE = {}           # user_id -> {"path": path, "time": timestamp}
CACHE_TTL = 600      

async def ensure_user_exists(conn, user):
    await conn.execute(
        """
        INSERT INTO users (user_id, name)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO NOTHING
        """,
        user.id,
        user.first_name or "Player"
    )

# 10 Minutes cache for avatars

def generate_members_thumbnail(
    cap_a_name: str,
    cap_b_name: str,
    cap_a_avatar_path: str,
    cap_b_avatar_path: str,
    group_name: str
):
    base = Image.open(MEMBERS_THUMB).convert("RGBA")
    draw = ImageDraw.Draw(base)
    W, H = base.size

    try:
        name_f = ImageFont.truetype(NAME_FONT, 36)
        group_f = ImageFont.truetype(NAME_FONT, 28)
        cap_f = ImageFont.truetype(NAME_FONT, 30)  # BIG CAP TEXT
    except:
        name_f = group_f = cap_f = ImageFont.load_default()

    # ─── GROUP NAME (TOP RIGHT) ───
    draw.text(
        (W - 45, 40),
        group_name[:24].upper(),
        font=group_f,
        fill=(230, 230, 230),
        anchor="rt"
    )

    def paste_circle(img_path, center, radius):
        try:
            avatar = Image.open(img_path).convert("RGBA").resize(
                (radius * 2, radius * 2), Image.LANCZOS
            )

            mask = Image.new("L", (radius * 2, radius * 2), 0)
            ImageDraw.Draw(mask).ellipse(
                (0, 0, radius * 2, radius * 2), fill=255
            )

            base.paste(
                avatar,
                (center[0] - radius, center[1] - radius),
                mask
            )

            # ─── CAPTAIN RING ───
            ring_radius = radius + 6
            draw.ellipse(
                (
                    center[0] - ring_radius,
                    center[1] - ring_radius,
                    center[0] + ring_radius,
                    center[1] + ring_radius
                ),
                outline=(255, 215, 140, 160),
                width=3
            )
        except:
            pass

    # ─── ALIGNMENT ───
    left_circle  = (W // 2 - 362, H // 2 + 2)
    right_circle = (W // 2 + 375, H // 2 + 2)
    radius_val = 194

    paste_circle(cap_a_avatar_path, left_circle, radius_val)
    paste_circle(cap_b_avatar_path, right_circle, radius_val)

    # ─── CAP TEXT (BETWEEN AVATAR & NAME) ───
    draw.text(
        (left_circle[0], left_circle[1] + radius_val + 20),
        "👑 CAPTAIN",
        font=cap_f,
        fill=(255, 215, 140),
        anchor="mm"
    )

    draw.text(
        (right_circle[0], right_circle[1] + radius_val + 20),
        "👑 CAPTAIN",
        font=cap_f,
        fill=(255, 215, 140),
        anchor="mm"
    )

    # ─── CAPTAIN NAMES (MOVED DOWN) ───
    draw.text(
        (left_circle[0], left_circle[1] + radius_val + 65),
        cap_a_name.upper(),
        font=name_f,
        fill=(255, 255, 255),
        anchor="mm"
    )

    draw.text(
        (right_circle[0], right_circle[1] + radius_val + 65),
        cap_b_name.upper(),
        font=name_f,
        fill=(255, 255, 255),
        anchor="mm"
    )

    buf = io.BytesIO()
    base.save(buf, "PNG", optimize=False)
    buf.seek(0)
    return buf


async def get_fast_avatar(client, user_id):
    """Avoids re-downloading if already in cache"""
    now = time.time()
    if user_id in AVATAR_CACHE:
        cache = AVATAR_CACHE[user_id]
        if now - cache['time'] < CACHE_TTL and os.path.exists(cache['path']):
            return cache['path']

    try:
        user = await client.get_users(user_id)
        if not user.photo: return None
        path = await client.download_media(user.photo.big_file_id)
        AVATAR_CACHE[user_id] = {'path': path, 'time': now}
        return path
    except:
        return None
        
@Client.on_message(filters.command("create_teams") & filters.group)
@host_only
async def create_teams(client, message):
    chat_id = message.chat.id
    user = message.from_user

    # 1. Immediate DB Check (Essential for game state)
    game = await get_active_game(chat_id)
    if not game:
        return await message.reply_text("No active game right now. Start one to play 🏏")

    # 2. Fast Memory Initialization
    # We do this BEFORE the reply to ensure the timer can attach instantly
    if chat_id not in ACTIVE_MATCHES:
        ACTIVE_MATCHES[chat_id] = {
            "chat_id": chat_id,
            "host_id": user.id,
            "host_name": user.first_name,
            "game_id": game["game_id"],
            "phase": "TEAM_A_JOIN",
            "join_timer_task": None,
            "teams": {"A": {"players": [], "runs": 0, "wickets": 0, "over_history": [0]}, 
                      "B": {"players": [], "runs": 0, "wickets": 0, "over_history": [0]}},
            "user_cache": {user.id: user.first_name}, # Cache host name immediately
            "players": {}
        }

    match = ACTIVE_MATCHES[chat_id]
    match["phase"] = "TEAM_A_JOIN"

    # 3. Fire-and-Forget DB Update (Don't wait for it to finish)
    asyncio.create_task(set_phase(chat_id, "TEAM_A_JOIN"))

    # 4. Instant Feedback
    await message.reply_text(
        "🎉 **𝗧𝗘𝗔𝗠 𝗖𝗥𝗘𝗔𝗧𝗜𝗢𝗡 𝗦𝗧𝗔𝗥𝗧𝗘𝗗**\n"
        "🌊 **Join Team A:** /join_teamA"
    )

    # 5. Timer Management
    if match.get("join_timer_task"):
        match["join_timer_task"].cancel()

    match["join_timer_task"] = asyncio.create_task(team_a_timer(client, chat_id))
    
# --- UPGRADED TIMERS WITH PHASE CHECKS ---

async def team_a_timer(client, chat_id):
    try:
        # ⏳ 30 seconds left
        await asyncio.sleep(15)

        match = ACTIVE_MATCHES.get(chat_id)
        if not match or match.get("phase") != "TEAM_A_JOIN":
            return

        await client.send_message(chat_id, "⏳ **30 seconds left** to join Team A /join_teamA ")

        # ⚠️ 10 seconds left
        await asyncio.sleep(20)

        match = ACTIVE_MATCHES.get(chat_id)
        if not match or match.get("phase") != "TEAM_A_JOIN":
            return

        await client.send_message(chat_id, "⚠️ **10 seconds remaining** to join Team A /join_teamA ")

        # ⏱️ Final 10 seconds
        await asyncio.sleep(10)

        # 🔄 Switch to Team B
        await set_phase(chat_id, "TEAM_B_JOIN")
        match = ACTIVE_MATCHES.get(chat_id)
        if match:
            match["phase"] = "TEAM_B_JOIN"
            await client.send_message(
                chat_id,
                "🔵 **TEAM A CLOSED** • Team B joining started\n➡️ Use /join_teamB"
            )
            match["join_timer_task"] = asyncio.create_task(
                team_b_timer(client, chat_id)
            )

    except asyncio.CancelledError:
        return

async def team_b_timer(client, chat_id):
    try:
        # ⏳ 30 seconds left
        await asyncio.sleep(15)

        match = ACTIVE_MATCHES.get(chat_id)
        if not match or match.get("phase") != "TEAM_B_JOIN":
            return
 
        await client.send_message(chat_id, "⏳ **30 seconds left** to join Team B /join_teamB")

        # ⚠️ 10 seconds left
        await asyncio.sleep(20)

        match = ACTIVE_MATCHES.get(chat_id)
        if not match or match.get("phase") != "TEAM_B_JOIN":
            return

        await client.send_message(chat_id, "⚠️ **10 seconds remaining** to join Team B /join_teamB")

        # ⏱️ Final 10 seconds
        await asyncio.sleep(10)

        # 🔒 Lock teams
        await set_phase(chat_id, "READY")
        match = ACTIVE_MATCHES.get(chat_id)
        if match:
            match["phase"] = "READY"
            match["join_timer_task"] = None
            await client.send_message(
                chat_id,
                "✅ **TEAM CREATION COMPLETE**\n🔒 Teams are now locked\n➡️ Proceed to /choose_cap"
            )

    except asyncio.CancelledError:
        return

import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ParseMode

# Assuming these are imported from your game logic files
# from plugins.game.team.init import get_active_game, set_phase

@Client.on_message(filters.command("rejointeams") & filters.group)
@host_only
async def rejoin_teams(client, message):
    chat_id = message.chat.id
    match = ACTIVE_MATCHES.get(chat_id)

    if not match:
        return await message.reply_text("❌ **No active match in memory.** Start with /create_teams.")

    game = await get_active_game(chat_id)
    if not game or game["phase"] not in ["READY", "TOSS_WAIT"]:
        return await message.reply_text("⚠️ **Cannot rejoin now. Match has already started!**")

    # 1️⃣ Update BOTH DB and RAM
    await set_phase(chat_id, "JOINING") 
    match["phase"] = "JOINING"

    await message.reply_text(
        "🔁 <b>TEAM JOINING REOPENED!</b>\n"
        "Use /join_teamA  or /join_teamB\n"
        "⏳ Open for <b>1 minutes</b>.",
        parse_mode=ParseMode.HTML
    )

    # 2️⃣ Cancel old timer and start new one
    if match.get("join_timer_task"):
        match["join_timer_task"].cancel()

    match["join_timer_task"] = asyncio.create_task(rejoin_timer(client, chat_id))

async def rejoin_timer(client, chat_id):
    """Background task to lock teams after 2 minutes."""
    try:
        await asyncio.sleep(60)

        # 🚨 SAFETY CHECK: If match ended or was deleted, stop immediately
        match = ACTIVE_MATCHES.get(chat_id)
        if not match or match.get("phase") != "JOINING":
            return

        # Lock the phase back to READY
        await set_phase(chat_id, "READY")
        match["phase"] = "READY"
        match["join_timer_task"] = None

        await client.send_message(
            chat_id,
            "🔒 <b>REJOIN CLOSED</b>\n"
            "Teams are now locked. Proceed to /choose_cap",
            parse_mode=ParseMode.HTML
        )
    except asyncio.CancelledError:
        pass
        
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
import random

@Client.on_message(filters.command(["join_teamA", "join_teamB"]) & filters.group)
async def join_team_logic(client, message):
    chat_id = message.chat.id
    user = message.from_user
    match = ACTIVE_MATCHES.get(chat_id)

    if not match:
        return await message.reply_text(
            "😴 No match running right now.\nStart one first and I’m in 🏏"
        )

    # 🧠 Determine team from command
    cmd = message.command[0].lower()
    target_team = "A" if "teama" in cmd else "B"

    # 1️⃣ CHECK: Already in THIS match
    if (
        user.id in match["teams"]["A"]["players"]
        or user.id in match["teams"]["B"]["players"]
    ):
        return await message.reply_text(
            "😏 You’re already on the field, champ.\n"
            "No need to join twice — this isn’t multiverse cricket 🌀"
        )

    # 2️⃣ CHECK: Already playing in ANOTHER active match
    async with db.pool.acquire() as conn:
        active_game = await conn.fetchrow(
            """
            SELECT g.chat_id, g.title 
            FROM game_players gp
            JOIN games g ON gp.game_id = g.game_id
            WHERE gp.user_id = $1 AND g.status = 'active'
            """,
            user.id
        )

        if active_game:
            group_title = active_game["title"] or "another group"
            return await message.reply_text(
                "🛑 Hold up!\n"
                f"You’re already battling it out in <b>{group_title}</b>.\n"
                "Finish that match first — no double-duty legends allowed 😤",
                parse_mode=ParseMode.HTML
            )

    # 3️⃣ PHASE CHECK
    current_phase = match.get("phase")
    allowed_phase = f"TEAM_{target_team}_JOIN"
    if current_phase not in (allowed_phase, "JOINING"):
        return await message.reply_text(
            f"🚪 Team {target_team} doors are closed.\n"
            "Missed the bus, maybe next match 🚌💨"
        )

    # 4️⃣ ADD PLAYER (Memory + DB) — FIXED
    async with db.pool.acquire() as conn:
        # ✅ CRITICAL FIX: ensure user exists in `users` table
        await ensure_user_exists(conn, user)

        # DB insert (FK safe now)
        await conn.execute(
            "INSERT INTO game_players (game_id, user_id, team) VALUES ($1, $2, $3)",
            match["game_id"], user.id, target_team
        )

    # 🔄 Sync Memory
    match["teams"][target_team]["players"].append(user.id)
    match["user_cache"][user.id] = user.first_name

    # 🎙️ RANDOM CRICKET JOIN COMMENTARY
    join_messages = [
        f"🔥 <b>{user.first_name}</b> walks into <b>Team {target_team}</b> with quiet confidence.\n"
        "Solid stance, steady heartbeat — this could be serious business 👀",

        f"🏏 <b>{user.first_name}</b> joins <b>Team {target_team}</b>.\n"
        "Fresh pads, fresh mindset… now let’s see if it’s class or collapse 😏",

        f"📊 <b>{user.first_name}</b> drafted into <b>Team {target_team}</b>.\n"
        "Intent looks aggressive — risk-reward ratio loading 📈📉",

        f"😈 <b>{user.first_name}</b> storms into <b>Team {target_team}</b>.\n"
        "Big confidence shown early… pressure’s officially on now 💥",
    ]

    await message.reply_text(
        random.choice(join_messages),
        parse_mode=ParseMode.HTML
    )

@Client.on_message(filters.command(["members", "teams"]) & filters.group)
async def members(client, message):
    chat_id = message.chat.id
    user = message.from_user
    match = ACTIVE_MATCHES.get(chat_id)

    # 1️⃣ Fetch Game from DB as fallback
    game = await get_active_game(chat_id)
    if not match and not game:
        return await message.reply_text("❌ **No active game available.**")

    # 2️⃣ Cooldown Logic (Host bypass)
    host_id = match.get("host_id") if match else game.get("host_id")
    if user.id != host_id:
        now = time.time()
        if chat_id in GROUP_COOLDOWN and (now - GROUP_COOLDOWN[chat_id]) < 10:
            remaining = 10 - (now - GROUP_COOLDOWN[chat_id])
            return await message.reply_text(
                f"⏳ **Slow down!** Try again in `{remaining:.1f}s`."
            )
        GROUP_COOLDOWN[chat_id] = now

    # 3️⃣ Phase Detection
    current_phase = match.get("phase") if match else game.get("phase")
    if match and (match.get("striker") or match.get("current_bowler")):
        current_phase = "LIVE"

    def get_status_text():
        if current_phase == "READY": return "⚖️ Setup / Toss"
        if current_phase in ("TEAM_A_JOIN", "TEAM_B_JOIN", "JOINING"): return "📝 Joining Phase"
        if current_phase == "LIVE": return "🏏 Match in Progress"
        return "🔄 Initializing"

    def team_activity(team_code):
        if current_phase == "LIVE" and match:
            return "𝗕𝗮𝘁𝘁𝗶𝗻𝗴" if match.get("batting_team") == team_code else "𝗕𝗼𝘄𝗹𝗶𝗻𝗴"
        if current_phase == "READY":
            return "𝗦𝗲𝘁𝘁𝗶𝗻𝗴 𝗨𝗽"
        return "𝗝𝗼𝗶𝗻𝗶𝗻𝗴..."

    # 4️⃣ Team List Formatter
    def format_team_list(team_code):
        players = match.get("teams", {}).get(team_code, {}).get("players", []) if match else []
        if not players:
            return "    ╰⊚ _No players joined_"

        lines = []
        for i, uid in enumerate(players, start=1):
            name = match.get("user_cache", {}).get(uid, "Player")
            tag = ""
            if uid == match.get("striker"): tag = " 🏏"
            elif uid == match.get("non_striker"): tag = " 🏃"
            elif uid == match.get("current_bowler"): tag = " ⚾"

            pdata = match.get("players", {}).get(uid, {})
            cap = " 👑" if pdata.get("is_captain") else ""
            out = " ❌" if pdata.get("is_out") else ""

            lines.append(f"    {i}. {name}{cap}{tag}{out}")
        return "\n".join(lines)

    # 5️⃣ Scores
    overs_val = match.get("overs") if match else game.get("overs", "N/A")
    host_name = match.get("host_name") if match else "Host"

    score_a = score_b = "0/0 (0.0 ov)"
    if match:
        for k in ("A", "B"):
            t = match["teams"].get(k, {})
            r, w, b = t.get("runs", 0), t.get("wickets", 0), t.get("balls", 0)
            ov = f"{b//6}.{b%6}"
            if k == "A": score_a = f"{r}/{w} ({ov} ov)"
            else: score_b = f"{r}/{w} ({ov} ov)"

    # 6️⃣ UI Text
    text = (
        "📊 **𝗠𝗔𝗧𝗖𝗛 𝗢𝗩𝗘𝗥𝗩𝗜𝗘𝗪**\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"👑 **𝗛𝗼𝘀𝘁:** {host_name}\n"
        f"⏳ **𝗢𝘃𝗲𝗿𝘀:** {overs_val} | 📍 **{get_status_text()}**\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"🌊 **𝗧𝗘𝗔𝗠 𝗔** - `{score_a}`\n"
        f"╰⊚ {team_activity('A')}\n"
        f"{format_team_list('A')}\n\n"
        f"🔥 **𝗧𝗘𝗔𝗠 𝗕** - `{score_b}`\n"
        f"╰⊚ {team_activity('B')}\n"
        f"{format_team_list('B')}\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        "✨ #CricketArena | @NexoraSystems"
    )

    # 7️⃣ Thumbnail Logic (HOST UNLIMITED)
    send_thumb = False
    cap_a = cap_b = None

    if match:
        for uid, pdata in match.get("players", {}).items():
            if pdata.get("is_captain"):
                if pdata.get("team") == "A": cap_a = uid
                elif pdata.get("team") == "B": cap_b = uid

    overs_set = bool(match and match.get("overs"))
    is_host = (user.id == host_id)

    if match and cap_a and cap_b and overs_set:
        if is_host:
            send_thumb = True
        else:
            if not match.get("members_thumb_sent"):
                send_thumb = True
                match["members_thumb_sent"] = True

    # 🔄 Refresh Button (ANYONE CAN USE)
    refresh_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_members")]
    ])

    # 8️⃣ Send Output
    try:
        if send_thumb:
            path_a = await get_fast_avatar(client, cap_a)
            path_b = await get_fast_avatar(client, cap_b)

            if path_a and path_b:
                thumb = generate_members_thumbnail(
                    cap_a_name=match["user_cache"].get(cap_a, "Captain A"),
                    cap_b_name=match["user_cache"].get(cap_b, "Captain B"),
                    cap_a_avatar_path=path_a,
                    cap_b_avatar_path=path_b,
                    group_name=message.chat.title or "Cricket Arena"
                )

                sent = await message.reply_photo(
                    photo=thumb,
                    caption=text,
                    reply_markup=refresh_markup
                )
                try:
                    await sent.pin(disable_notification=True)
                except ChatAdminRequired:
                    pass
            else:
                await message.reply_text(text)
        else:
            await message.reply_photo(
                photo=MEMBERS_IMAGE,
                caption=text,
                reply_markup=refresh_markup
            )

    except Exception as e:
        print(f"[MEMBERS ERROR]: {e}")
        await message.reply_text(text)


@Client.on_callback_query(filters.regex("^refresh_members$"))
async def refresh_members_callback(client, cq):
    message = cq.message
    chat_id = message.chat.id

    match = ACTIVE_MATCHES.get(chat_id)
    game = await get_active_game(chat_id)

    if not match and not game:
        return await cq.answer("No active match.", show_alert=True)

    current_phase = match.get("phase") if match else game.get("phase")
    if match and (match.get("striker") or match.get("current_bowler")):
        current_phase = "LIVE"

    def get_status_text():
        if current_phase == "READY": return "⚖️ Setup / Toss"
        if current_phase in ("TEAM_A_JOIN", "TEAM_B_JOIN", "JOINING"): return "📝 Joining Phase"
        if current_phase == "LIVE": return "🏏 Match in Progress"
        return "🔄 Initializing"

    def team_activity(team_code):
        if current_phase == "LIVE" and match:
            return "𝗕𝗮𝘁𝘁𝗶𝗻𝗴" if match.get("batting_team") == team_code else "𝗕𝗼𝘄𝗹𝗶𝗻𝗴"
        if current_phase == "READY":
            return "𝗦𝗲𝘁𝘁𝗶𝗻𝗴 𝗨𝗽"
        return "𝗝𝗼𝗶𝗻𝗶𝗻𝗴..."

    def format_team_list(team_code):
        players = match.get("teams", {}).get(team_code, {}).get("players", []) if match else []
        if not players:
            return "    ╰⊚ _No players joined_"

        lines = []
        for i, uid in enumerate(players, start=1):
            name = match.get("user_cache", {}).get(uid, "Player")
            tag = ""
            if uid == match.get("striker"): tag = " 🏏"
            elif uid == match.get("non_striker"): tag = " 🏃"
            elif uid == match.get("current_bowler"): tag = " ⚾"

            pdata = match.get("players", {}).get(uid, {})
            cap = " 👑" if pdata.get("is_captain") else ""
            out = " ❌" if pdata.get("is_out") else ""

            lines.append(f"    {i}. {name}{cap}{tag}{out}")
        return "\n".join(lines)

    score_a = score_b = "0/0 (0.0 ov)"
    if match:
        for k in ("A", "B"):
            t = match["teams"].get(k, {})
            r, w, b = t.get("runs", 0), t.get("wickets", 0), t.get("balls", 0)
            ov = f"{b//6}.{b%6}"
            if k == "A": score_a = f"{r}/{w} ({ov} ov)"
            else: score_b = f"{r}/{w} ({ov} ov)"

    overs_val = match.get("overs") if match else game.get("overs", "N/A")
    host_name = match.get("host_name") if match else "Host"

    text = (
        "📊 **𝗠𝗔𝗧𝗖𝗛 𝗢𝗩𝗘𝗥𝗩𝗜𝗘𝗪**\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"👑 **𝗛𝗼𝘀𝘁:** {host_name}\n"
        f"⏳ **𝗢𝘃𝗲𝗿𝘀:** {overs_val} | 📍 **{get_status_text()}**\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"🌊 **𝗧𝗘𝗔𝗠 𝗔** - `{score_a}`\n"
        f"╰⊚ {team_activity('A')}\n"
        f"{format_team_list('A')}\n\n"
        f"🔥 **𝗧𝗘𝗔𝗠 𝗕** - `{score_b}`\n"
        f"╰⊚ {team_activity('B')}\n"
        f"{format_team_list('B')}\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        "✨ #CricketArena | @NexoraSystems"
    )

    await message.edit_caption(
        caption=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_members")]
        ])
    )

    await cq.answer("Updated ✔️")

import random
from pyrogram import Client, filters

@Client.on_message(filters.command("testmem") & filters.group)
async def test_members_thumbnail(client, message):
    chat = message.chat

    # 1. Fetch recent group members (limited for speed)
    try:
        members = []
        async for m in client.get_chat_members(chat.id, limit=50):
            if m.user and not m.user.is_bot:
                members.append(m.user)

        if len(members) < 2:
            return await message.reply_text("❌ Need at least 2 users to test thumbnail.")

        # 2. Pick 2 random users
        cap_a, cap_b = random.sample(members, 2)

    except Exception as e:
        print(e)
        return await message.reply_text("❌ Failed to fetch members.")

    # 3. Get avatars (cached)
    path_a = await get_fast_avatar(client, cap_a.id)
    path_b = await get_fast_avatar(client, cap_b.id)

    if not path_a or not path_b:
        return await message.reply_text("❌ Could not fetch avatars.")

    # 4. Generate thumbnail
    thumb = generate_members_thumbnail(
        cap_a_name=cap_a.first_name or "Captain A",
        cap_b_name=cap_b.first_name or "Captain B",
        cap_a_avatar_path=path_a,
        cap_b_avatar_path=path_b,
        group_name=chat.title or "Cricket Arena"
    )

    # 5. Send result
    await message.reply_photo(
        photo=thumb,
        caption=(
            "🧪 **MEMBERS THUMBNAIL TEST**\n"
            f"👑 Captain A: {cap_a.first_name}\n"
            f"👑 Captain B: {cap_b.first_name}\n\n"
            "_This is a test render only_"
        ),
        parse_mode=ParseMode.MARKDOWN
    )


@Client.on_message(filters.command("add") & filters.group)
@host_only
async def add_player(client, message):
    chat_id = message.chat.id
    args = message.text.split(maxsplit=2)

    # 1️⃣ Check for active match in DB and Memory
    game = await get_active_game(chat_id)
    match = ACTIVE_MATCHES.get(chat_id)

    if not game or not match:
        return await message.reply_text(
            "😴 No match running here.\nStart one first and then we’ll add players 🔥"
        )

    # 2️⃣ Validation & Team Assignment
    if len(args) < 2 or args[1].upper() not in ("A", "B"):
        return await message.reply_text(
            "🤔 That didn’t look right.\n\n"
            "👉 Use it like this:\n"
            "<code>/add A</code> or <code>/add B</code>\n"
            "↪ Reply to a user or mention them",
            parse_mode=ParseMode.HTML
        )

    team = args[1].upper()
    game_id = game["game_id"]
    targets = []

    # 3️⃣ Collect targets
    if message.reply_to_message:
        targets.append(message.reply_to_message.from_user)

    if len(args) == 3:
        raw_users = args[2].replace("\n", " ").split()
        for raw in raw_users:
            try:
                user = await client.get_users(raw)
                targets.append(user)
            except Exception:
                targets.append(raw)

    if not targets:
        return await message.reply_text(
            "👀 I see no players here.\nReply to someone or mention them properly."
        )

    success_list = []
    failed_details = []

    async with db.pool.acquire() as conn:
        for target in targets:
            try:
                if isinstance(target, str):
                    failed_details.append(f"• <code>{target}</code> — invalid user")
                    continue

                # 🚦 Already playing somewhere else?
                other = await user_in_other_game(target.id, chat_id)
                if other:
                    failed_details.append(
                        f"• {target.first_name} — already in another match"
                    )
                    continue

                # 🚫 Already in this match?
                exists = await conn.fetchval(
                    "SELECT 1 FROM game_players WHERE game_id=$1 AND user_id=$2",
                    game_id, target.id
                )
                if exists:
                    failed_details.append(
                        f"• {target.first_name} — already added"
                    )
                    continue

                # ✅ FK FIX: ensure user exists (NO /start needed)
                await ensure_user_exists(conn, target)

                # 🧠 Insert DB
                await conn.execute(
                    "INSERT INTO game_players (game_id, user_id, team) VALUES ($1, $2, $3)",
                    game_id, target.id, team
                )

                # 🔄 Sync Memory
                if target.id not in match["teams"][team]["players"]:
                    match["teams"][team]["players"].append(target.id)

                match["players"].setdefault(target.id, {
                    "runs": 0,
                    "balls_faced": 0,
                    "wickets": 0,
                    "runs_conceded": 0,
                    "balls_bowled": 0,
                    "bowling_balls": [],
                    "team": team,
                    "is_out": False,
                    "sixes_count": 0,
                    "fours_count": 0,
                    "late_join": True if match.get("started") else False
                })

                match["user_cache"][target.id] = target.first_name or "Player"
                success_list.append(target.mention)

            except Exception as e:
                print("ADD PLAYER ERROR:", e)
                failed_details.append(
                    f"• {target.first_name if hasattr(target, 'first_name') else target} — failed"
                )

    # ── RESPONSE ──

    # ✅ Single add → clean & friendly
    if len(success_list) == 1 and len(targets) == 1:
        return await message.reply_text(
            f"✅ {success_list[0]} added to <b>Team {team}</b>.\n"
            "All set. Let’s play 🏏",
            parse_mode=ParseMode.HTML
        )

    # 🎨 CLEAN MULTI-ADD SUMMARY (AESTHETIC)
    team_icon = "🌊" if team == "A" else "🔥"

    res = (
        f"{team_icon} <b>Team {team} Update</b>\n"
        f"────────────\n"
    )

    if success_list:
        res += "✅ <b>Added</b>\n"
        for p in success_list:
            res += f"• {p}\n"
        res += "\n"

    if failed_details:
        res += "⚠️ <b>Skipped</b>\n"
        for f in failed_details:
            res += f"{f}\n"

    await message.reply_text(
        res,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

@Client.on_message(filters.command("remove") & filters.group)
@host_only
async def remove_player(client, message):
    chat_id = message.chat.id
    args = message.text.split(maxsplit=1)

    game = await get_active_game(chat_id)
    if not game:
        return await message.reply_text(
            "😴 No match running here.\nNothing to remove… yet.",
            parse_mode=ParseMode.HTML
        )

    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(args) == 2:
        try:
            target = await client.get_users(args[1])
        except Exception:
            pass

    if not target:
        return await message.reply_text(
            "🤔 Who are we removing?\n\n"
            "👉 Reply to a player or pass their ID/username.",
            parse_mode=ParseMode.HTML
        )

    game_id = game["game_id"]
    match = ACTIVE_MATCHES.get(chat_id)

    # 🛑 SAFETY CHECK: Player currently on field
    if match:
        active_on_field = [
            match.get("striker"),
            match.get("non_striker"),
            match.get("current_bowler")
        ]
        if target.id in active_on_field:
            return await message.reply_text(
                "🚫 Easy there, chief.\n"
                "That player is **in action right now** 🏏\n\n"
                "Wait for the over to finish or for the batter to walk back.",
                parse_mode=ParseMode.HTML
            )

    async with db.pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM game_players WHERE game_id=$1 AND user_id=$2",
            game_id, target.id
        )

        if not exists:
            return await message.reply_text(
                "👀 That player isn’t even part of this match.\n"
                "Wrong universe?",
                parse_mode=ParseMode.HTML
            )

        # 1️⃣ Remove from Database
        await conn.execute(
            "DELETE FROM game_players WHERE game_id=$1 AND user_id=$2",
            game_id, target.id
        )

    # 2️⃣ Sync Live Memory
    if match:
        for team_key in ["A", "B"]:
            if target.id in match["teams"][team_key]["players"]:
                match["teams"][team_key]["players"].remove(target.id)

        match["players"].pop(target.id, None)
        match["user_cache"].pop(target.id, None)

    await message.reply_text(
        f"🧹 {target.mention} has been removed.\n"
        "Roster updated. Drama reduced 😌",
        parse_mode=ParseMode.HTML
    )


@Client.on_message(filters.command("shiftteam") & filters.group)
async def shift_team(client, message):
    chat_id = message.chat.id
    user = message.from_user
    match = ACTIVE_MATCHES.get(chat_id)

    game = await get_active_game(chat_id)
    if not game:
        return await message.reply_text(
            "😴 No match running right now.\n"
            "Team hopping is closed for today.",
            parse_mode=ParseMode.HTML
        )

    # Use memory phase first, fallback to DB
    phase = match.get("phase") if match else game["phase"]

    # 🚫 Block shifting once match progresses
    if phase in ("LIVE", "READY", "STARTED", "INNINGS_1", "INNINGS_2"):
        return await message.reply_text(
            "🔒 Teams are locked now.\n"
            "Once the match gears up, no more switching sides 🏏",
            parse_mode=ParseMode.HTML
        )

    game_id = game["game_id"]

    # 🔢 Shift limit check
    shifts_used = await get_shift_count(game_id, user.id)
    if shifts_used >= 2:
        return await message.reply_text(
            "🚫 Shift limit reached.\n"
            "You’ve already used **2/2** team switches.\n"
            "No more musical chairs 🎶",
            parse_mode=ParseMode.HTML
        )

    async with db.pool.acquire() as conn:
        player = await conn.fetchrow(
            "SELECT team FROM game_players WHERE game_id=$1 AND user_id=$2",
            game_id, user.id
        )

        if not player:
            return await message.reply_text(
                "👀 You’re not even in this match yet.\n"
                "Join a team first, then we’ll talk.",
                parse_mode=ParseMode.HTML
            )

        current = player["team"]
        new_team = "B" if current == "A" else "A"

        # 1️⃣ Update Database
        await conn.execute(
            "UPDATE game_players SET team=$1 WHERE game_id=$2 AND user_id=$3",
            new_team, game_id, user.id
        )

    # 🚀 2️⃣ Sync with Live Memory
    if match:
        if user.id in match["teams"][current]["players"]:
            match["teams"][current]["players"].remove(user.id)

        if user.id not in match["teams"][new_team]["players"]:
            match["teams"][new_team]["players"].append(user.id)

        if user.id in match["players"]:
            match["players"][user.id]["team"] = new_team

    # 3️⃣ Increment shift counter
    await increment_shift(game_id, user.id)
    shifts_used += 1

    await message.reply_text(
        f"🔁 Team switch successful!\n\n"
        f"👤 <b>{user.first_name}</b> moved to <b>Team {new_team}</b><b>{shifts_used}/2</b>\n"
        "Choose wisely… last chances don’t come back 😏",
        parse_mode=ParseMode.HTML
    )
