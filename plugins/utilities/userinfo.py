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

LOADING_STICKER = "CAACAgUAAxkBAALPAmm6Mnqzn153LcLGy-QexrqQakTqAAK1CQAC6b85V0ohe3zS5QecHgQ"


def _format_form(recent_form: str) -> str:
    mapping = {'W': '🟢', 'L': '🔴'}
    circles = [mapping.get(c, '⬜') for c in (recent_form or '')]
    while len(circles) < 5:
        circles.append('⬜')
    return ' '.join(circles)


def _profile_buttons(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧬 Cricket DNA", callback_data=f"show_dna:{uid}"),
            InlineKeyboardButton("⚔️ 1v1 Stats", callback_data=f"show_duel:{uid}"),
        ]
    ])


async def _get_user_stats(uid: int):
    try:
        await db.ensure_pool()
        return await db.db["user_stats"].find_one({"user_id": uid})
    except Exception:
        return None


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

    try:
        stats = await _get_user_stats(uid)
    except Exception:
        return await message.reply_text("⚠️ Database busy. Please try again in a moment.")

    if not stats:
        return await message.reply_text("❌ <b>No stats found</b>\nPlay some matches first!", parse_mode=ParseMode.HTML)

    sticker_msg = None
    try:
        sticker_msg = await message.reply_sticker(LOADING_STICKER)
    except Exception:
        pass

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
    form_display = _format_form(stats.get("recent_form", ""))

    caption = (
        f"🏏 <b>𝗖𝗔𝗥𝗘𝗘𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘</b>\n"
        f"👤 <b>Player:</b> ⏤͟͞{target_user.first_name}\n"
        f"🎖️ <b>Tier:</b> {tier}\n"
        f"🧬 <b>Title:</b> {mister}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"📊 <b>Form:</b> {form_display}\n"
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
        f"✅ Wins: {won} | ❌ Losses: {lost}\n\n"
        "🤝 <b>𝗣𝗔𝗥𝗧𝗡𝗘𝗥𝗦𝗛𝗜𝗣</b>\n"
        f"🏏 Best Partnership: {stats.get('best_partnership', 0)} runs\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"#CricketLegacy | {date.today()}"
    )

    try:
        from plugins.utilities.profile_card import generate_card, download_user_photo
        photo_bytes = await download_user_photo(client, uid)
        card_buf = generate_card(photo_bytes, target_user, dict(stats))
        card_buf.name = "profile_card.png"

        if sticker_msg:
            try:
                await sticker_msg.delete()
            except Exception:
                pass

        await message.reply_photo(photo=card_buf, caption=caption, parse_mode=ParseMode.HTML, reply_markup=_profile_buttons(uid))

    except Exception as e:
        if sticker_msg:
            try:
                await sticker_msg.delete()
            except Exception:
                pass
        await message.reply_photo(photo=PROFILE_IMG, caption=caption, parse_mode=ParseMode.HTML, reply_markup=_profile_buttons(uid))

CATEGORIES = {
    "runs": ("🏏 Most Runs", "runs"),
    "wickets": ("🎯 Most Wickets", "wickets"),
    "ducks": ("🦆 Highest Ducks", "ducks"),
    "fifties": ("⭐ Most Fifties", "fifties"),
    "centuries": ("🔥 Most Centuries", "centuries"),
    "moms": ("🏅 Most MOMs", "moms"),
    "best_captain": ("🧑‍✈️ Best Captain", "wins"),
    "best_partnership": ("🤝 Best Partnership", "best_partnership"),
}

async def get_home_text(user):
    uid = user.id
    try:
        await db.ensure_pool()
        stats = await db.db["user_stats"].find_one({"user_id": uid})
    except Exception:
        return f"📊 <b>Welcome, <a href='tg://user?id={uid}'>{user.first_name}</a>!</b>\n\nDatabase warming up. Try again shortly."

    if not stats:
        return f"📊 <b>Welcome, <a href='tg://user?id={uid}'>{user.first_name}</a>!</b>\n\n⚠️ Your stats are being initialized.\nPlay at least one match and try again."

    name = stats.get("first_name") or user.first_name
    runs = stats.get("runs", 0)
    rank = await db.db["user_stats"].count_documents({"runs": {"$gt": runs}}) + 1
    matches = stats.get("matches", 0)
    wins = stats.get("wins", 0)
    win_rate = (wins / matches * 100) if matches > 0 else 0.0

    return (
        f"📊 <b>𝗪𝗲𝗹𝗰𝗼𝗺𝗲, <a href='tg://user?id={uid}'>{name}</a>!</b>\n"
        f"🏅 <b>Global Rank:</b> #{rank}\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"🏃 <b>Runs:</b> <code>{int(runs)}</code>\n"
        f"⚾ <b>Wickets:</b> <code>{int(stats.get('wickets', 0))}</code>\n"
        f"🎮 <b>Matches:</b> <code>{int(matches)}</code>\n"
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

    await db.ensure_pool()
    col = db.db["user_stats"]
    users_col = db.db["users"]

    if category_key == "best_captain":
        pipeline = [
            {"$match": {"matches": {"$gt": 0}}},
            {"$addFields": {"display_val": {"$cond": [{"$gt": ["$matches", 0]}, {"$multiply": [{"$divide": ["$wins", "$matches"]}, 100]}, 0]}}},
            {"$sort": {"display_val": -1, "matches": -1}},
            {"$skip": offset},
            {"$limit": limit},
        ]
        count_match = {"matches": {"$gt": 0}}
    else:
        pipeline = [
            {"$sort": {db_column: -1}},
            {"$skip": offset},
            {"$limit": limit},
            {"$addFields": {"display_val": f"${db_column}"}},
        ]
        count_match = {}

    top_players = await col.aggregate(pipeline).to_list(length=limit)
    total = await col.count_documents(count_match)

    user_stat = await col.find_one({"user_id": uid}, {"runs": 1, db_column: 1, "matches": 1, "wins": 1})
    pos_text = "N/A"
    if user_stat:
        if category_key == "best_captain":
            user_wr = (user_stat.get("wins", 0) / user_stat.get("matches", 1) * 100) if user_stat.get("matches", 0) > 0 else 0
            above = await col.count_documents({"matches": {"$gt": 0}, "$expr": {"$gt": [{"$multiply": [{"$divide": ["$wins", "$matches"]}, 100]}, user_wr]}})
        else:
            above = await col.count_documents({db_column: {"$gt": user_stat.get(db_column, 0)}})
        pos_text = f"{above + 1}/{total}"

    text = f"<b>{label}</b>\n🔹 Your Position: {pos_text}\n\n"

    if not top_players:
        return text + "<i>No data yet.</i>", 0

    for i, row in enumerate(top_players, start=offset + 1):
        user_doc = await users_col.find_one({"user_id": row["user_id"]}, {"name": 1})
        p_name = (user_doc or {}).get("name") or row.get("first_name") or "Player"
        val = row.get("display_val", 0) or 0
        formatted_val = f"{val:.1f}%" if category_key == "best_captain" else f"{int(val)}"
        text += f"{i}. <b>{p_name}</b> = <code>{formatted_val}</code> ({int(row.get('matches', 0))} matches)\n\n"

    return text, total

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


@Client.on_callback_query(filters.regex("^show_dna:"))
async def show_dna_callback(client, query: CallbackQuery):
    await query.answer()
    uid = int(query.data.split(":")[1])

    from plugins.utilities.analyze import _get_personality as get_personality
    DNA_PROFILES = {
        "Powerhouse 💪": {"tagline": "Run-machine. The scoreboard belongs to you.", "trait": "Unstoppable batting dominance.", "tip": "Keep piling runs — centuries are your calling card.", "color": "🔴"},
        "Aggressive ⚔️": {"tagline": "Big swings, bigger boundaries.", "trait": "High-octane strike rate with explosive hitting.", "tip": "Channel the aggression — six every over is the goal.", "color": "🟠"},
        "Spin Wizard 🌀": {"tagline": "Batters can't read you. That's the point.", "trait": "Low economy, high wickets — bowling is your art.", "tip": "Stay patient, vary pace, and watch them crumble.", "color": "🟣"},
        "Strategic 🧠": {"tagline": "Calculated, composed, and always one step ahead.", "trait": "High average, consistent performer.", "tip": "Play the long game — patience is your superpower.", "color": "🔵"},
        "Finisher 🏆": {"tagline": "Best when the match is on the line.", "trait": "Top win rate and Man of the Match performances.", "tip": "Keep delivering in pressure moments.", "color": "🟡"},
        "Lucky Charm 🍀": {"tagline": "Unpredictable, chaotic, but somehow it works.", "trait": "Rising star — personality still forming.", "tip": "Play more matches to unlock your true potential.", "color": "🟢"},
    }

    try:
        stats = await _get_user_stats(uid)
    except Exception:
        await query.answer("DB error, try again.", show_alert=True)
        return

    try:
        target = await client.get_users(uid)
        display_name = target.first_name
    except Exception:
        display_name = "Player"

    if not stats:
        text = (
            "🧬 <b>Cricket DNA</b>\n\n"
            "🍀 <b>Lucky Charm</b>\n"
            "<i>Play some matches to unlock your DNA!</i>"
        )
    else:
        dna = get_personality(dict(stats))
        info = DNA_PROFILES[dna]
        runs = int(stats.get("runs") or 0)
        wickets = int(stats.get("wickets") or 0)
        matches = int(stats.get("matches") or 0)
        wins = int(stats.get("wins") or 0)
        balls_faced = int(stats.get("balls_faced") or 0)
        balls_bowled = int(stats.get("balls_bowled") or 0)
        runs_conceded = int(stats.get("runs_conceded") or 0)
        sixes = int(stats.get("sixes") or 0)
        centuries = int(stats.get("centuries") or 0)
        moms = int(stats.get("moms") or 0)

        sr = f"{runs / balls_faced * 100:.1f}" if balls_faced > 0 else "—"
        eco = f"{runs_conceded / (balls_bowled / 6):.2f}" if balls_bowled > 0 else "—"
        wr = f"{wins / max(matches, 1) * 100:.0f}%"

        text = (
            f"🧬 <b>Cricket DNA ❖ {display_name}</b>\n"
            "────┈┄┄╌╌╌╌┄┄┈────\n\n"
            f"{info['color']} <b>{dna}</b>\n"
            f"<i>{info['tagline']}</i>\n\n"
            f"⚡ <b>Trait:</b> {info['trait']}\n"
            f"💡 <b>Tip:</b> {info['tip']}\n\n"
            "📊 <b>Your Numbers:</b>\n"
            f"➥ 🏃 Runs: <b>{runs}</b>  |  Wickets: <b>{wickets}</b>\n"
            f"➥ ⚡ SR: <b>{sr}</b>  |  Eco: <b>{eco}</b>\n"
            f"➥ 💯 Centuries: <b>{centuries}</b>  |  MOMs: <b>{moms}</b>\n"
            f"➥ 🔥 Sixes: <b>{sixes}</b>  |  Win Rate: <b>{wr}</b>\n\n"
            "────┈┄┄╌╌╌╌┄┄┈────\n"
            "✨ <i>DNA evolves with every match you play.</i>"
        )

    back_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Profile", callback_data=f"back_profile:{uid}")]
    ])

    try:
        await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=back_btn)
    except Exception:
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_btn)


@Client.on_callback_query(filters.regex("^show_duel:"))
async def show_duel_callback(client, query: CallbackQuery):
    await query.answer()
    uid = int(query.data.split(":")[1])

    try:
        await db.ensure_pool()
        row = await db.db["duel_stats"].find_one({"user_id": uid})
    except Exception:
        await query.answer("DB error, try again.", show_alert=True)
        return

    try:
        target = await client.get_users(uid)
        display_name = target.first_name
    except Exception:
        display_name = "Player"

    if not row:
        text = (
            f"⚔️ <b>1v1 Duel Stats — {display_name}</b>\n\n"
            "No duel matches played yet!\n"
            "Use <b>⚔️ 1v1 Duel</b> from your group to challenge opponents."
        )
    else:
        matches = int(row.get("matches") or 0)
        wins = int(row.get("wins") or 0)
        losses = int(row.get("losses") or 0)
        runs = int(row.get("runs") or 0)
        wickets = int(row.get("wickets") or 0)
        highest = int(row.get("highest_score") or 0)
        ducks = int(row.get("ducks") or 0)
        wr = f"{wins / max(matches, 1) * 100:.1f}%"

        text = (
            f"⚔️ <b>1v1 Duel Stats</b>\n"
            f"👤 <b>{display_name}</b>\n"
            "────┈┄┄╌╌╌╌┄┄┈────\n\n"
            f"🎮 Duels Played: <b>{matches}</b>\n"
            f"🏆 Wins: <b>{wins}</b> | ❌ Losses: <b>{losses}</b>\n"
            f"📈 Win Rate: <b>{wr}</b>\n\n"
            f"🏏 Total Runs: <b>{runs}</b>\n"
            f"🎯 Wickets Taken: <b>{wickets}</b>\n"
            f"🔥 Highest Score: <b>{highest}</b>\n"
            f"🦆 Ducks: <b>{ducks}</b>\n"
            "────┈┄┄╌╌╌╌┄┄┈────\n"
            "⚔️ <i>Duels sharpen your instincts!</i>"
        )

    back_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Profile", callback_data=f"back_profile:{uid}")]
    ])

    try:
        await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=back_btn)
    except Exception:
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_btn)


@Client.on_callback_query(filters.regex("^back_profile:"))
async def back_profile_callback(client, query: CallbackQuery):
    await query.answer()
    uid = int(query.data.split(":")[1])

    try:
        stats = await _get_user_stats(uid)
    except Exception:
        await query.answer("DB error.", show_alert=True)
        return

    if not stats:
        await query.answer("No profile found.", show_alert=True)
        return

    try:
        target = await client.get_users(uid)
    except Exception:
        await query.answer("User not found.", show_alert=True)
        return

    runs = int(stats.get("runs") or 0)
    balls_faced = int(stats.get("balls_faced") or 0)
    matches = int(stats.get("matches") or 0)
    ducks = int(stats.get("ducks") or 0)
    won = int(stats.get("wins") or 0)
    lost = int(stats.get("losses") or 0)
    wickets = int(stats.get("wickets") or 0)
    balls_bowled = int(stats.get("balls_bowled") or 0)
    runs_conceded = int(stats.get("runs_conceded") or 0)
    moms = int(stats.get("moms") or 0)

    out_count = matches - int(stats.get("not_outs") or 0)
    bat_avg = runs / out_count if out_count > 0 else float(runs)
    sr = (runs / balls_faced * 100) if balls_faced > 0 else 0.0
    econ = (runs_conceded / (balls_bowled / 6)) if balls_bowled > 0 else 0.0
    bowl_avg = (runs_conceded / wickets) if wickets > 0 else 0.0
    bowl_sr = (balls_bowled / wickets) if wickets > 0 else 0.0
    win_rate = (won / matches * 100) if matches > 0 else 0.0
    mister = calculate_title(stats)
    performance_score, tier = calculate_rank(stats)
    form_display = _format_form(stats.get("recent_form", ""))

    caption = (
        f"🏏 <b>𝗖𝗔𝗥𝗘𝗘𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘</b>\n"
        f"👤 <b>Player:</b> ⏤͟͞{target.first_name}\n"
        f"🎖️ <b>Tier:</b> {tier}\n"
        f"🧬 <b>Title:</b> {mister}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"📊 <b>Form:</b> {form_display}\n"
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
        f"✅ Wins: {won} | ❌ Losses: {lost}\n\n"
        "🤝 <b>𝗣𝗔𝗥𝗧𝗡𝗘𝗥𝗦𝗛𝗜𝗣</b>\n"
        f"🏏 Best Partnership: {stats.get('best_partnership', 0)} runs\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"#CricketLegacy | {date.today()}"
    )

    try:
        await query.message.edit_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=_profile_buttons(uid))
    except Exception:
        await query.message.edit_text(caption, parse_mode=ParseMode.HTML, reply_markup=_profile_buttons(uid))
