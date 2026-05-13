import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.games import get_active_game
from database.connection import db
from utils.permissions import host_only
import random
from pyrogram.enums import ParseMode
from plugins.game.team import init_match
from plugins.game.team import ACTIVE_MATCHES
from utils.mentions import mention_html
from html import escape
from Assets.files import RUN_VIDEOS


def safe_mention(user):
    name = escape(user.first_name or "Player")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def sync_captain_flags(match, team):
    captain_id = match["teams"][team].get("captain_id")
    for uid, pdata in match["players"].items():
        if pdata.get("team") == team:
            pdata["is_captain"] = (uid == captain_id)


async def display_user(client, user_id):
    try:
        user = await client.get_users(user_id)
        if user.username:
            return f"@{user.username}"
        else:
            return user.mention
    except Exception:
        return f"<code>{user_id}</code>"


async def get_username(client, user_id: int):
    try:
        u = await client.get_users(user_id)
        return f"@{u.username}" if u.username else u.first_name
    except Exception:
        return "Unknown"


def uname(user):
    return f"@{user.username}" if user.username else user.first_name


@Client.on_message(filters.command("choose_cap") & filters.group)
@host_only
async def choose_captain(client, message):
    chat_id = message.chat.id

    game = await get_active_game(chat_id)
    if not game:
        return await message.reply_text("**No active game.**")

    game_id = str(game["game_id"])

    await db.ensure_pool()
    captains = await db.db["game_players"].find(
        {"game_id": game_id, "is_captain": True},
        {"team": 1}
    ).to_list(length=10)

    if len(captains) == 2:
        return await message.reply_text(
            "🧢 **CAPTAINS ALREADY SELECTED**\n"
            "Use /changecap to modify captains."
        )

    if len(captains) == 1:
        taken = captains[0]["team"]
        remaining = "B" if taken == "A" else "A"
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"Become Team {remaining} Captain", callback_data=f"cap_{remaining}")
        ]])
        return await message.reply_text(
            "🧢 **CAPTAIN SELECTION IN PROGRESS**\n"
            f"Team {remaining} must choose a captain.",
            reply_markup=buttons
        )

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("Become Team A Captain", callback_data="cap_A"),
        InlineKeyboardButton("Become Team B Captain", callback_data="cap_B"),
    ]])

    await message.reply_text(
        "🧢 **CAPTAIN SELECTION OPEN**\n"
        "Each team must choose one leader to proceed ⏳",
        reply_markup=buttons
    )


@Client.on_callback_query(filters.regex("^cap_"))
async def set_captain(client, query):
    chat_id = query.message.chat.id
    user = query.from_user
    team = query.data.split("_")[1]

    game = await get_active_game(chat_id)
    match = ACTIVE_MATCHES.get(chat_id)

    if not game:
        return await query.answer("No active game.", show_alert=True)

    game_id = str(game["game_id"])
    await db.ensure_pool()

    player = await db.db["game_players"].find_one({"game_id": game_id, "user_id": user.id, "team": team})
    if not player:
        return await query.answer("You are not in this team.", show_alert=True)

    existing = await db.db["game_players"].find_one({"game_id": game_id, "team": team, "is_captain": True})
    if existing:
        return await query.answer("Captain already chosen for this team.", show_alert=True)

    await db.db["game_players"].update_one(
        {"game_id": game_id, "user_id": user.id},
        {"$set": {"is_captain": True}}
    )

    if match:
        if user.id not in match["players"]:
            match["players"][user.id] = {
                "runs": 0, "balls_faced": 0, "wickets": 0, "runs_conceded": 0,
                "balls_bowled": 0, "bowling_balls": [], "team": team,
                "is_out": False, "sixes_count": 0, "fours_count": 0,
            }
        for uid, pdata in match["players"].items():
            if pdata.get("team") == team:
                pdata["is_captain"] = False
        match["players"][user.id]["is_captain"] = True
        match["teams"].setdefault(team, {})["captain_id"] = user.id
        match["user_cache"][user.id] = user.first_name

    caps = await db.db["game_players"].find(
        {"game_id": game_id, "is_captain": True},
        {"team": 1, "user_id": 1}
    ).to_list(length=10)

    if len(caps) == 1:
        remaining = "B" if team == "A" else "A"
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"Become Team {remaining} Captain", callback_data=f"cap_{remaining}")
        ]])
        return await query.message.edit_text(
            f"⚡ <b>CAPTAIN CONFIRMED</b>\n"
            f"────┈┄┄╌╌╌╌┄┄┈────\n"
            f"👤 <b>Leader:</b> {user.mention} ⚔{team}\n"
            f"────┈┄┄╌╌╌╌┄┄┈────\n"
            f"Waiting for Team {remaining} captain...",
            reply_markup=buttons,
            parse_mode=ParseMode.HTML
        )

    capA = next(c for c in caps if c["team"] == "A")
    capB = next(c for c in caps if c["team"] == "B")

    capA_name = match["user_cache"].get(capA["user_id"], "Captain A") if match else "Captain A"
    capB_name = match["user_cache"].get(capB["user_id"], "Captain B") if match else "Captain B"

    await query.message.edit_text(
        "⚡ <b>𝗖𝗔𝗣𝗧𝗔𝗜𝗡𝗦 𝗟𝗢𝗖𝗞𝗘𝗗 𝗜𝗡</b>\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"🌊 <b>Team A:</b> {capA_name}\n"
        f"🔥 <b>Team B:</b> {capB_name}\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        "The match is about to begin!",
        parse_mode=ParseMode.HTML
    )

    # Team names: non-blocking background ask (if setting enabled)
    if match:
        try:
            from database.group_settings import get_setting as _gs_tn
            from plugins.game.team.team_names import ask_team_names
            if await _gs_tn(chat_id, "team_names"):
                asyncio.create_task(
                    ask_team_names(client, match, capA["user_id"], capB["user_id"])
                )
        except Exception:
            pass

    await send_toss(client, chat_id, game_id)


async def send_toss(client, chat_id, game_id):
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("Head", callback_data="toss_head"),
        InlineKeyboardButton("Tails", callback_data="toss_tail"),
    ]])
    await client.send_message(
        chat_id,
        "🪙 **TOSS TIME**\n"
        "Choose wisely • Head or Tails decides the fate",
        reply_markup=buttons
    )


@Client.on_callback_query(filters.regex("^toss_"))
async def toss_handler(client, query):
    chat_id = query.message.chat.id
    caller = query.from_user
    choice = query.data.split("_")[1].lower()

    if choice not in ["head", "tail"]:
        return await query.answer("Invalid choice.", show_alert=True)

    game = await get_active_game(chat_id)
    match = ACTIVE_MATCHES.get(chat_id)

    if not game:
        return await query.answer("No active game.", show_alert=True)

    game_id = str(game["game_id"])
    await db.ensure_pool()

    caller_cap = await db.db["game_players"].find_one(
        {"game_id": game_id, "user_id": caller.id, "is_captain": True},
        {"team": 1}
    )
    if not caller_cap:
        return await query.answer("Only captains can participate in the toss.", show_alert=True)

    game_row = await db.db["games"].find_one({"game_id": game_id}, {"toss_winner": 1})
    if game_row and game_row.get("toss_winner"):
        return await query.answer("Toss already completed.", show_alert=True)

    opponent = await db.db["game_players"].find_one(
        {"game_id": game_id, "is_captain": True, "user_id": {"$ne": caller.id}},
        {"user_id": 1}
    )
    if not opponent:
        return await query.answer("Opponent not found.", show_alert=True)

    result = random.choice(["head", "tail"])
    caller_won = (choice == result)
    winner_id = caller.id if caller_won else opponent["user_id"]

    update_result = await db.db["games"].update_one(
        {"game_id": game_id, "toss_winner": None},
        {"$set": {"toss_winner": winner_id}}
    )
    if update_result.modified_count == 0:
        return await query.answer("Toss already completed.", show_alert=True)

    if match:
        match["toss_winner"] = winner_id

    winner_mention = await display_user(client, winner_id)

    await query.message.edit_text(
        f"🪙 <b>TOSS RESULT:</b> <code>{result.upper()}</code>\n"
        f"🏆 <b>Winner:</b> {winner_mention}",
        parse_mode=ParseMode.HTML
    )

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏏 Bat First", callback_data="decide_bat"),
        InlineKeyboardButton("🎯 Bowl First", callback_data="decide_bowl"),
    ]])

    await client.send_message(
        chat_id,
        f"🏏 <b>DECISION TIME</b>\n"
        f"{winner_mention}, choose your side.",
        reply_markup=buttons,
        parse_mode=ParseMode.HTML
    )


@Client.on_callback_query(filters.regex("^decide_"))
async def decide_play(client, query):
    chat_id = query.message.chat.id
    user = query.from_user
    decision = query.data.split("_")[1]
    match = ACTIVE_MATCHES.get(chat_id)

    await db.ensure_pool()

    game = await db.db["games"].find_one(
        {"chat_id": chat_id, "status": "active"},
        {"game_id": 1, "toss_winner": 1}
    )

    if not game:
        return await query.answer("No active game.", show_alert=True)

    game_id = str(game["game_id"])

    if game.get("toss_winner") != user.id:
        return await query.answer("⛔ Only the toss winner can decide!", show_alert=True)

    cap = await db.db["game_players"].find_one(
        {"game_id": game_id, "user_id": user.id, "is_captain": True},
        {"team": 1}
    )
    if not cap:
        return await query.answer("Error: Captain team data not found.", show_alert=True)

    my_team = cap["team"]
    other_team = "B" if my_team == "A" else "A"

    batting = my_team if decision == "bat" else other_team
    bowling = other_team if decision == "bat" else my_team

    await db.db["games"].update_one(
        {"game_id": game_id},
        {"$set": {"batting_team": batting, "bowling_team": bowling, "phase": "overs_setup"}}
    )

    if match:
        match["batting_team"] = batting
        match["bowling_team"] = bowling
        match["phase"] = "overs_setup"

    await query.message.edit_text(
        f"📢 <b>DECISION LOCKED</b>\n"
        f"────┈┄┄╌╌╌╌┄┄┈────\n"
        f"🏆 <b>Toss Winner:</b> {user.first_name}\n"
        f"🏏 <b>Choice:</b> {decision.upper()} FIRST\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"🔵 <b>Team {batting}</b> will Bat.\n"
        f"🔴 <b>Team {bowling}</b> will Bowl.",
        parse_mode=ParseMode.HTML
    )

    await client.send_message(
        chat_id,
        "⚙️ <b>𝗡𝗘𝗫𝗧 𝗦𝗧𝗘𝗣</b>\n"
        "Host, please select match overs using <code>/set_overs</code>\n"
        "<i>Or use buttons if the prompt is visible.</i>",
        parse_mode=ParseMode.HTML
    )


@Client.on_message(filters.command("set_overs") & filters.group)
@host_only
async def set_overs(client, message):
    chat_id = message.chat.id

    game = await get_active_game(chat_id)
    if not game:
        return await message.reply_text("❌ **No active game found.**")

    if not game.get("batting_team"):
        return await message.reply_text(
            "🪙 **Toss not completed yet.**\n"
            "Finish the toss before setting overs."
        )

    if game.get("overs"):
        return await message.reply_text(f"📊 **Overs already set:** `{game['overs']}`")

    buttons = []
    row = []
    for i in range(1, 21):
        row.append(InlineKeyboardButton(text=f"{i} Overs", callback_data=f"setovers_{i}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await message.reply_text(
        "📊 **SET MATCH OVERS**\n"
        "Select the total overs for this match:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@Client.on_callback_query(filters.regex("^setovers_"))
async def overs_callback(client, query):
    chat_id = query.message.chat.id
    user = query.from_user
    overs = int(query.data.split("_")[1])

    game = await get_active_game(chat_id)
    if not game:
        return await query.answer("No active game.", show_alert=True)

    if user.id != game["host_id"]:
        return await query.answer("Only the host can set overs.", show_alert=True)

    if game.get("overs"):
        return await query.answer("Overs already locked.", show_alert=True)

    game_id = str(game["game_id"])
    await db.ensure_pool()
    await db.db["games"].update_one({"game_id": game_id}, {"$set": {"overs": overs}})

    if chat_id in ACTIVE_MATCHES:
        ACTIVE_MATCHES[chat_id]["overs"] = overs
        ACTIVE_MATCHES[chat_id]["phase"] = "LIVE"

    await query.message.edit_text(
        f"📊 **OVERS CONFIRMED**\n"
        f"Match will be played for `{overs}` overs.",
        parse_mode=ParseMode.MARKDOWN
    )

    caps = await db.db["game_players"].find(
        {"game_id": game_id, "is_captain": True},
        {"team": 1, "user_id": 1}
    ).to_list(length=10)

    cap_map = {c["team"]: c["user_id"] for c in caps}

    bat_team = game["batting_team"]
    bowl_team = game["bowling_team"]

    bat_cap_user = await client.get_users(cap_map[bat_team])
    bowl_cap_user = await client.get_users(cap_map[bowl_team])

    await client.send_message(
        chat_id,
        (
            "✅ <b>GAME SETUP COMPLETE</b>\n\n"
            f"🏏 <b>Batting Team:</b> Team {bat_team}\n"
            f"👤 <b>Captain:</b> {bat_cap_user.first_name}\n\n"
            f"🎯 <b>Bowling Team:</b> Team {bowl_team}\n"
            f"👤 <b>Captain:</b> {bowl_cap_user.first_name}\n\n"
            "📌 <b>NEXT STEP</b>\n"
            "Batting captain → <code>/batting &lt;number&gt;</code> to select <b>STRIKER</b>"
        ),
        parse_mode=ParseMode.HTML
    )


@Client.on_message(filters.command("batting") & filters.group)
async def set_batting(client, message):
    chat_id = message.chat.id
    user = message.from_user
    args = message.text.strip().split(maxsplit=1)

    if len(args) != 2 or not args[1].isdigit():
        return await message.reply_text(
            "❓ <b>Usage:</b> <code>/batting &lt;num&gt;</code>",
            parse_mode=ParseMode.HTML
        )

    idx = int(args[1]) - 1

    match = ACTIVE_MATCHES.get(chat_id)
    if match and match.get("mode") == "Solo":
        return

    game = await get_active_game(chat_id)
    if not game:
        return await message.reply_text(
            "😴 <b>No match right now.</b>\n/Start one first and we'll cook 🔥",
            parse_mode=ParseMode.HTML
        )

    if not game.get("overs"):
        return await message.reply_text(
            "⛔ <b>Overs not set yet!</b>\n\n"
            "📊 Host must set overs first using:\n"
            "<code>/set_overs</code>",
            parse_mode=ParseMode.HTML
        )

    game_id = str(game["game_id"])
    batting_team = game["batting_team"]

    team_players = match.get("teams", {}).get(batting_team, {}).get("players", []) if match else []

    if idx < 0 or idx >= len(team_players):
        return await message.reply_text(f"❌ <b>Invalid player number.</b> Choose between 1 and {len(team_players)}.")

    selected_id = team_players[idx]

    await db.ensure_pool()
    players_db = await db.db["game_players"].find(
        {"game_id": game_id, "team": batting_team},
        {"user_id": 1, "is_captain": 1}
    ).to_list(length=50)

    is_cap = any(p["user_id"] == user.id and p.get("is_captain") for p in players_db)
    if user.id != game.get("host_id") and not is_cap:
        return await message.reply_text(
            "🚫 <b>Captain's and Host call only.</b>\nSpectators, enjoy the drama 😌",
            parse_mode=ParseMode.HTML
        )

    if match and match.get("players", {}).get(selected_id, {}).get("is_out"):
        return await message.reply_text("💀 <b>That batter is history.</b>\nOnce out, always out 😬")

    if match and selected_id in (match.get("striker"), match.get("non_striker")):
        return await message.reply_text("⚠️ <b>Already batting!</b>\nNo cloning allowed 🧬")

    role = "striker" if match.get("striker") is None else "non_striker"

    async def background_db_update():
        try:
            await db.db["game_players"].update_one(
                {"game_id": game_id, "user_id": selected_id},
                {"$set": {"role": role}}
            )
        except Exception:
            pass

    asyncio.create_task(background_db_update())

    try:
        player_obj = await client.get_users(selected_id)
        mention = f"<a href='tg://user?id={selected_id}'>{player_obj.first_name}</a>"
        if match:
            match["user_cache"][selected_id] = player_obj.first_name
    except Exception:
        mention = "Player"

    if match:
        match[role] = selected_id
        match["players"].setdefault(selected_id, {
            "runs": 0, "balls_faced": 0, "wickets": 0, "runs_conceded": 0,
            "balls_bowled": 0, "bowling_balls": [], "team": batting_team, "is_out": False
        })

    if role == "striker" and match.get("non_striker") is None:
        return await message.reply_text(
            f"🏏 <b>STRIKER LOCKED 🔒</b> {mention} takes the strike.\n"
            f"Ready to set the partner?\n\n"
            f"👉 Use <code>/batting</code> to choose the non-striker.",
            parse_mode=ParseMode.HTML
        )

    if match and match.get("striker") and match.get("non_striker"):
        if match.get("total_balls", 0) > 0:
            await message.reply_text(
                f"🧢 <b>NEW BATTER IN!</b>\n"
                f"🟢 {mention} walks out to the middle.\n"
                f"Pressure on. Game on 😈",
                parse_mode=ParseMode.HTML
            )

            if match.get("current_bowler"):
                match["prompt_dispatched"] = False
                match["bowled"] = False
                match["batted"] = False
                match["last_bowl"] = None

                if "timeouts" in match:
                    for r in ["bowler", "batter"]:
                        task = match["timeouts"].get(r, {}).get("task")
                        if task:
                            try:
                                task.cancel()
                            except Exception:
                                pass

                from plugins.game.team.state import start_first_ball
                await start_first_ball(client, match)
                return
            else:
                return await message.reply_text(
                    "🎯 <b>Batters are set.</b>\n"
                    "Bowling Captain, it's your move.\n"
                    "Choose your bowler using /bowling",
                    parse_mode=ParseMode.HTML
                )
        else:
            match["phase"] = "READY"
            match["current_bowler"] = None

            opening_video = RUN_VIDEOS["Opening"][0]

            return await client.send_video(
                chat_id=chat_id,
                video=opening_video,
                caption=(
                    f"🏏 <b>OPENERS READY!</b>\n"
                    f"🟢 <b>Striker:</b> {match['user_cache'].get(match['striker'])}\n"
                    f"🟡 <b>Non-Striker:</b> {match['user_cache'].get(match['non_striker'])}\n"
                    f"🎯 <b>Bowling Captain</b>, choose your opening bowler:\n"
                    f"<code>/bowling &lt;number&gt;</code>"
                ),
                parse_mode=ParseMode.HTML
            )


@Client.on_message(filters.command("bowling") & filters.group)
async def set_bowler(client, message):
    chat_id = message.chat.id
    user = message.from_user
    args = message.text.strip().split(maxsplit=1)

    if len(args) != 2 or not args[1].isdigit():
        return await message.reply_text(
            "❓ <b>Usage:</b> <code>/bowling <number></code>",
            parse_mode=ParseMode.HTML
        )

    idx = int(args[1]) - 1

    match = ACTIVE_MATCHES.get(chat_id)
    if match and match.get("mode") == "Solo":
        return

    game = await get_active_game(chat_id)
    if not game:
        return await message.reply_text(
            "😕 <b>No match found.</b> /Start a game and unleash the bowlers 🎯",
            parse_mode=ParseMode.HTML
        )

    game_id = str(game["game_id"])
    bowling_team = game["bowling_team"]
    batting_team = game["batting_team"]

    await db.ensure_pool()

    try:
        batters, bowling_players_db, team_a_rows, team_b_rows = await asyncio.gather(
            db.db["game_players"].find(
                {"game_id": game_id, "team": batting_team, "role": {"$in": ["striker", "non_striker"]}},
                {"user_id": 1, "role": 1}
            ).to_list(length=10),
            db.db["game_players"].find(
                {"game_id": game_id, "team": bowling_team},
                {"user_id": 1, "is_captain": 1, "team": 1}
            ).sort("joined_at", 1).to_list(length=50),
            db.db["game_players"].find(
                {"game_id": game_id, "team": "A"},
                {"user_id": 1}
            ).to_list(length=50),
            db.db["game_players"].find(
                {"game_id": game_id, "team": "B"},
                {"user_id": 1}
            ).to_list(length=50)
        )
    except Exception as e:
        print(f"❌ DB Fetch Error (/bowling): {e}")
        return await message.reply_text(
            "⚠️ <b>Database busy.</b>\nPlease try again in a moment.",
            parse_mode=ParseMode.HTML
        )

    striker_id = next((p["user_id"] for p in batters if p["role"] == "striker"), None)
    non_striker_id = next((p["user_id"] for p in batters if p["role"] == "non_striker"), None)

    if not striker_id or not non_striker_id:
        return await message.reply_text(
            f"🏏 <b>Batters not ready!</b>\nTeam <b>{batting_team}</b> must set both openers using <code>/batting</code> first.",
            parse_mode=ParseMode.HTML
        )

    is_cap_or_host = (user.id == game["host_id"]) or any(p["user_id"] == user.id and p.get("is_captain") for p in bowling_players_db)
    if not is_cap_or_host:
        return await message.reply_text("🚫 <b>Captain or Host only.</b> Everyone else — grab popcorn 🍿", parse_mode=ParseMode.HTML)

    if match and match.get("teams") and bowling_team in match["teams"]:
        team_players = match["teams"][bowling_team].get("players", [])
        if idx < 0 or idx >= len(team_players):
            return await message.reply_text(f"❌ <b>Wrong number.</b> Choose between 1 and {len(team_players)}.", parse_mode=ParseMode.HTML)
        bowler_id = team_players[idx]
    else:
        if idx < 0 or idx >= len(bowling_players_db):
            return await message.reply_text(f"❌ <b>Wrong number.</b> Choose between 1 and {len(bowling_players_db)}.", parse_mode=ParseMode.HTML)
        bowler_id = bowling_players_db[idx]["user_id"]

    if match:
        if match.get("current_bowler"):
            return await message.reply_text("⚾ <b>Ball already in hand.</b> Let this over finish first 👀", parse_mode=ParseMode.HTML)
        if bowler_id == match.get("last_over_bowler"):
            last_name = match.get("last_over_bowler_name", "The previous bowler")
            return await message.reply_text(f"🚫 <b>No back-to-back overs!</b> {last_name} needs a breather 😤", parse_mode=ParseMode.HTML)

    try:
        bowler_user = await client.get_users(bowler_id)
    except Exception:
        return await message.reply_text("❌ <b>User not found in Telegram.</b>")

    team_data = {"A": [r["user_id"] for r in team_a_rows], "B": [r["user_id"] for r in team_b_rows]}

    if match:
        if client:
            match["client"] = client

        match.update({"current_bowler": bowler_id, "phase": "LIVE"})
        match["user_cache"][bowler_id] = bowler_user.first_name

        match["players"].setdefault(bowler_id, {
            "runs": 0, "balls_faced": 0, "wickets": 0, "runs_conceded": 0,
            "balls_bowled": 0, "bowling_balls": [], "team": bowling_team, "is_out": False
        })

        await message.reply_text(f"⚾ <b>{bowler_user.first_name}</b> is now bowling.")
        from plugins.game.team.state import start_first_ball
        match["prompt_dispatched"] = False
        asyncio.create_task(start_first_ball(client, match))

    else:
        await message.reply_text(f"⚾ <b>{bowler_user.first_name}</b> takes the opening over.")

        new_match = await init_match(
            chat_id=chat_id, game_id=game_id, host_id=game["host_id"],
            teams=team_data, overs=game["overs"], batting_team=batting_team,
            bowling_team=bowling_team, striker=striker_id,
            non_striker=non_striker_id, bowler=bowler_id, client=client
        )

        from plugins.game.team.state import start_first_ball
        asyncio.create_task(start_first_ball(client, new_match))
