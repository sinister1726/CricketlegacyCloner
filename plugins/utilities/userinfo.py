import time
from datetime import date

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.enums import ParseMode

from database.connection import db
from Assets.files import LEADERBOARD_IMG, PROFILE_IMG

COOLDOWN = {}

NEW_RANKS = [
    ("🪵 Rookie", 0),
    ("🥉 Bronze", 1200),
    ("🥈 Silver", 2600),
    ("🥇 Gold", 4500),
    ("💠 Platinum", 7200),
    ("🔷 Diamond", 10500),
    ("🔥 Elite", 14500),
    ("⚔️ Warrior", 19000),
    ("👑 Champion", 24500),
    ("🏆 Master", 31000),
    ("💎 Grandmaster", 38500),
    ("🐉 Mythic", 47000),
    ("🌌 Legendary", 56500),
    ("🌀 Immortal", 67000),
    ("🌠 Cosmic", 79000),
    ("🔮 Ascendant", 91000),
    ("🌟 KING", 109000),
    ("🐐 GOAT", 150000),
    ("🛐 Cricket God", 293000),
]

def calculate_rank(stats):
    runs = stats.get("runs", 0)
    wickets = stats.get("wickets", 0)
    matches = stats.get("matches", 0)

    balls_faced = stats.get("balls_faced", 0)
    runs_conceded = stats.get("runs_conceded", 0)
    balls_bowled = stats.get("balls_bowled", 0)

    fifties = stats.get("fifties", 0)
    centuries = stats.get("centuries", 0)
    hat_tricks = stats.get("hat_tricks", 0)

    outs = max(1, matches - stats.get("not_outs", 0))
    avg = runs / outs
    sr = (runs / balls_faced * 100) if balls_faced > 0 else 0

    econ = (runs_conceded / (balls_bowled / 6)) if balls_bowled > 0 else 10

    batting_score = (avg * 20) + (sr * 0.6) + (fifties * 25) + (centuries * 60)
    bowling_score = (wickets * 18) + (hat_tricks * 120) - (econ * 12)
    experience_score = matches * 8

    performance_score = (batting_score * 0.45) + (bowling_score * 0.35) + (experience_score * 0.20)

    rank_name = NEW_RANKS[0][0]
    level = "I"

    for i in range(len(NEW_RANKS)):
        name, start = NEW_RANKS[i]
        end = NEW_RANKS[i + 1][1] if i + 1 < len(NEW_RANKS) else start + 999999

        if start <= performance_score < end:
            span = end - start
            chunk = span / 3

            if performance_score < start + chunk:
                level = "I"
            elif performance_score < start + (2 * chunk):
                level = "II"
            else:
                level = "III"

            rank_name = name
            break

    return int(performance_score), f"{rank_name} {level}"

def calculate_title(stats):
    runs = stats.get("runs", 0)
    wickets = stats.get("wickets", 0)
    matches = stats.get("matches", 0)
    moms = stats.get("moms", 0)
    ducks = stats.get("ducks", 0)

    balls_faced = stats.get("balls_faced", 0)
    balls_bowled = stats.get("balls_bowled", 0)
    runs_conceded = stats.get("runs_conceded", 0)

    fifties = stats.get("fifties", 0)
    centuries = stats.get("centuries", 0)
    hat_tricks = stats.get("hat_tricks", 0)

    avg = runs / max(1, matches - stats.get("not_outs", 0))
    sr = (runs / balls_faced * 100) if balls_faced > 0 else 0
    econ = (runs_conceded / (balls_bowled / 6)) if balls_bowled > 0 else 99

    if runs >= 1000 and wickets >= 100: return "🐐 Complete Cricketer"
    if sr >= 320 and runs >= 800: return "🧨 Mr. Striker"
    if econ <= 4.5 and wickets >= 80: return "🧊 Economy God"
    if centuries >= 5: return "👑 Century Lord"
    if hat_tricks >= 3: return "🎩 Hat-Trick King"
    if moms >= 15: return "👑 Match Dominator"
    if sr >= 280 and runs >= 600: return "⚡ Explosive Finisher"
    if wickets >= 120: return "☠️ Wicket Reaper"
    if avg >= 65 and runs >= 700: return "🧠 Run Machine"
    if runs >= 700 and wickets >= 70: return "⚖️ True All-Rounder"
    if econ <= 5.5 and wickets >= 60: return "🎯 Precision Bowler"
    if moms >= 100: return "🔥 Game Breaker"
    if centuries >= 20: return "💯 Big Match Player"
    if fifties >= 25: return "⭐ Consistency Master"
    if avg >= 75 and runs >= 5500: return "🏏 Anchor King"
    if wickets >= 250: return "⚔️ Strike Bowler"
    if sr >= 300 and runs >= 3500: return "🔥 Power Hitter"
    if moms >= 36: return "⭐ Impact Player"
    if matches >= 8350: return "🏛 Cricket Legend"
    if matches >= 500: return "🧱 Veteran Warrior"
    if ducks >= 25: return "🦆 Walking Duck"

    return "—"

@Client.on_message(filters.command(["userinfo", "profile", "userstats"]))
async def userinfo(client, message):
    current_time = time.time()
    target_user = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target_user = await client.get_users(int(arg) if arg.isdigit() else arg)
        except:
            return await message.reply_text("❌ <b>User not found.</b>\nUse reply / username / user_id", parse_mode=ParseMode.HTML)
    else:
        target_user = message.from_user

    uid = target_user.id

    if uid == message.from_user.id:
        if uid in COOLDOWN and (current_time - COOLDOWN[uid]) < 5:
            remaining = 5 - (current_time - COOLDOWN[uid])
            return await message.reply_text(f"⏳ **Slow down!** Try again in {remaining:.1f}s")
        COOLDOWN[uid] = current_time

    from utils.dbpass import safe_fetchrow

    try:
        stats = await safe_fetchrow("SELECT * FROM user_stats WHERE user_id=$1", uid)
    except Exception:
        return await message.reply_text("⚠️ Database busy. Please try again in a moment.")

    if not stats:
        return await message.reply_text("❌ <b>No stats found</b>\nPlay some matches first!", parse_mode=ParseMode.HTML)

    runs = stats.get("runs", 0)
    balls_faced = stats.get("balls_faced", 0)
    matches = stats.get("matches", 0)
    ducks = stats.get("ducks", 0)
    won = stats.get("wins", 0)
    lost = stats.get("losses", 0)
    wickets = stats.get("wickets", 0)
    balls_bowled = stats.get("balls_bowled", 0)
    runs_conceded = stats.get("runs_conceded", 0)
    moms = stats.get("moms", 0)

    out_count = matches - stats.get("not_outs", 0)
    bat_avg = runs / out_count if out_count > 0 else float(runs)
    sr = (runs / balls_faced * 100) if balls_faced > 0 else 0.0

    econ = (runs_conceded / (balls_bowled / 6)) if balls_bowled > 0 else 0.0
    bowl_avg = (runs_conceded / wickets) if wickets > 0 else 0.0
    bowl_sr = (balls_bowled / wickets) if wickets > 0 else 0.0

    win_rate = (won / matches * 100) if matches > 0 else 0.0
    mister = calculate_title(stats)
    performance_score, tier = calculate_rank(stats)

    text = (
        f"🏏 <b>𝗖𝗔𝗥𝗘𝗘𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘</b>\n"
        f"👤 <b>Player:</b> ⏤͟͞{target_user.first_name}\n"
        f"🎖️ <b>Tier:</b> {tier}\n"
        f"🧬 <b>Mister:</b> {mister}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n\n"
        "📊 <b>𝗢𝗩𝗘𝗥𝗔𝗟𝗟 𝗦𝗧𝗔𝗧𝗦</b>\n"
        f"🎮 Matches: {matches}\n"
        f"🏆 Highest: {stats.get('highest_score', 0)}\n"
        f"🏅 MOMs: {moms}\n"
        f"📈 Performance: {performance_score}\n\n"
        "🏏 <b>𝗕𝗔𝗧𝗧𝗜𝗡𝗚</b>\n"
        f"🏃 Runs: {runs} | 📈 Avg: {bat_avg:.2f}\n"
        f"⚡ S/R: {sr:.2f}\n"
        f"💥 6s: {stats.get('sixes', 0)} • 4s: {stats.get('fours', 0)}\n"
        f"🔥 100s: {stats.get('centuries', 0)} • 50s: {stats.get('fifties', 0)}\n"
        f"🦆 Ducks: {ducks}\n\n"
        "🎯 <b>𝗕𝗢𝗪𝗟𝗜𝗡𝗚</b>\n"
        f"⚾ Wickets: {wickets}\n"
        f"🎯 Econ: {econ:.2f} | 📈 Avg: {bowl_avg:.2f}\n"
        f"⚡ S/R: {bowl_sr:.2f}\n"
        f"🎩 Hat-Tricks: {stats.get('hat_tricks', 0)}\n\n"
        "🧢 <b>𝗟𝗘𝗔𝗗𝗘𝗥𝗦𝗛𝗜𝗣</b>\n"
        f"📈 Win Rate: {win_rate:.1f}%\n"
        f"✅ Wins: {won} | ❌ Losses: {lost}\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"#CricQuest | {date.today()}"
    )

    await message.reply_photo(photo=PROFILE_IMG, caption=text, parse_mode=ParseMode.HTML)

CATEGORIES = {
    "runs": ("🏏 Most Runs", "runs"),
    "wickets": ("🎯 Most Wickets", "wickets"),
    "ducks": ("🦆 Highest Ducks", "ducks"),
    "fifties": ("⭐ Most Fifties", "fifties"),
    "centuries": ("🔥 Most Centuries", "centuries"),
    "moms": ("🏅 Most MOMs", "moms"),
    "best_captain": ("🧑‍✈️ Best Captain", "wins")
}

async def get_home_text(user):
    uid = user.id
    from utils.dbpass import safe_fetchrow

    try:
        stats = await safe_fetchrow("SELECT *, (SELECT COUNT(*) + 1 FROM user_stats WHERE runs > t.runs) as rank, CASE WHEN matches > 0 THEN (wins::float / matches * 100) ELSE 0 END as current_win_rate FROM user_stats t WHERE user_id = $1", uid)
    except Exception:
        return f"📊 <b>Welcome, {user.first_name}!</b>\n\nDatabase warming up. Try again shortly."

    if not stats:
        return f"📊 <b>Welcome, {user.first_name}!</b>\n\n⚠️ Your stats are being initialized.\nPlay at least one match and try again."

    name = stats.get("first_name") or user.first_name
    win_rate = stats.get("current_win_rate", 0)

    return (
        f"📊 <b>𝗪𝗲𝗹𝗰𝗼𝗺𝗲, {name}!</b>\n"
        f"🏅 <b>Global Rank:</b> #{int(stats['rank'])}\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"🏃 <b>Runs:</b> <code>{int(stats.get('runs', 0))}</code>\n"
        f"⚾ <b>Wickets:</b> <code>{int(stats.get('wickets', 0))}</code>\n"
        f"🎮 <b>Matches:</b> <code>{int(stats.get('matches', 0))}</code>\n"
        f"🏅 <b>MOMs:</b> <code>{int(stats.get('moms', 0))}</code>\n"
        f"🧑‍✈️ <b>Captain Win Rate:</b> <code>{win_rate:.1f}%</code>\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        "Select a category below to view Global Rankings:"
    )

async def build_rank_text(client, uid, category_key, offset=0):
    if category_key not in CATEGORIES:
        return "❌ <b>Error:</b> Invalid category selected.", 0

    label, db_column = CATEGORIES[category_key]
    limit = 10

    async with db.pool.acquire() as conn:
        if category_key == "best_captain":
            query = "SELECT user_id, first_name, matches, (wins::float / NULLIF(matches, 0) * 100) as display_val FROM user_stats WHERE matches > 0 ORDER BY display_val DESC NULLS LAST, matches DESC LIMIT $1 OFFSET $2"
            order_clause = "(wins::float / NULLIF(matches, 0)) DESC NULLS LAST"
            where_clause = "WHERE matches > 0"
        else:
            query = f"SELECT user_id, first_name, matches, {db_column} as display_val FROM user_stats ORDER BY display_val DESC NULLS LAST LIMIT $1 OFFSET $2"
            order_clause = f"{db_column} DESC NULLS LAST"
            where_clause = ""

        top_players = await conn.fetch(query, limit, offset)

        user_pos_query = f"SELECT position, total_count FROM (SELECT user_id, RANK() OVER (ORDER BY {order_clause}) as position, COUNT(*) OVER() as total_count FROM user_stats {where_clause}) as stats WHERE user_id = $1"
        user_pos = await conn.fetchrow(user_pos_query, uid)

    pos_text = f"{user_pos['position']}/{user_pos['total_count']}" if user_pos else "N/A"
    text = f"<b>{label}</b>\n🔹 Your Position: {pos_text}\n\n"

    if not top_players:
        return text + "<i>No data yet.</i>", 0

    for i, row in enumerate(top_players, start=offset + 1):
        p_name = row["first_name"] or "User"
        val = row["display_val"]
        formatted_val = f"{val:.1f}%" if category_key == "best_captain" else f"{int(val)}"
        text += f"{i}. <b>{p_name}</b> = <code>{formatted_val}</code> ({int(row['matches'])} matches)\n\n"

    return text, user_pos["total_count"] if user_pos else 0

def get_main_menu():
    btns, row = [], []
    for key, (label, _) in CATEGORIES.items():
        row.append(InlineKeyboardButton(label, callback_data=f"rankview:{key}:0"))
        if len(row) == 2:
            btns.append(row)
            row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

@Client.on_message(filters.command("user_ranks"))
async def ranks_command(client, message: Message):
    text = await get_home_text(message.from_user)
    await message.reply_photo(photo=LEADERBOARD_IMG, caption=text, reply_markup=get_main_menu())

@Client.on_callback_query(filters.regex("^rankview:"))
async def rank_view_callback(client, query: CallbackQuery):
    data = query.data.split(":")
    category, offset = data[1], int(data[2])

    text, total = await build_rank_text(client, query.from_user.id, category, offset)

    btns = []
    nav = []
    if offset > 0: nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"rankview:{category}:{offset-10}"))
    if offset + 10 < total: nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"rankview:{category}:{offset+10}"))
    if nav: btns.append(nav)

    btns.append([InlineKeyboardButton("🔙 Main Menu", callback_data="rank_main")])

    try: await query.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(btns))
    except: await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btns))

@Client.on_callback_query(filters.regex("^rank_main"))
async def rank_main_menu(client, query: CallbackQuery):
    text = await get_home_text(query.from_user)
    try: await query.message.edit_caption(caption=text, reply_markup=get_main_menu())
    except: await query.message.edit_text(text, reply_markup=get_main_menu())
    
