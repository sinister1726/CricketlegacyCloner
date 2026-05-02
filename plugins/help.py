from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from database.users import add_user


HELP_HOME_TEXT = (
    "📘 <b>Help & Guide</b>\n\n"
    "Not sure where to start? I got you 😌\n"
    "Pick a topic below and we’ll break it down."
)


def _home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎮 How to Play", callback_data="help_play"),
                InlineKeyboardButton("👥 Team Mode", callback_data="help_team"),
            ],
            [
                InlineKeyboardButton("🧍 Solo Mode", callback_data="help_solo"),
                InlineKeyboardButton("⚔️ Duel Mode", callback_data="help_duel"),
            ],
            [
                InlineKeyboardButton("👤 User Commands", callback_data="help_user"),
                InlineKeyboardButton("📋 All Commands", callback_data="help_commands"),
            ],
        ]
    )


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Back", callback_data="help_back")]]
    )


HELP_PLAY_TEXT = (
    "🎮 <b>How to Play</b>\n\n"
    "🏏 <b>During the Game</b>\n"
    "• Solo Mode: Batters choose <b>1–6</b>\n"
    "• Team Mode: Batters choose <b>0–6</b>\n"
    "• Bowlers send <b>1–6</b> in bot DM\n\n"
    "📊 <b>Scoring</b>\n"
    "• Same number = <b>OUT ❌</b>\n"
    "• Batter chooses 0 = Dot ball\n"
    "• Otherwise = runs scored\n\n"
    "✨ <b>Special Rules</b>\n"
    "• Odd runs → strike change\n"
    "• 6 balls = 1 over\n"
    "• Over end → strike change\n\n"
    "⏱ <b>Timeouts</b>\n"
    "• 1 minute per move\n"
    "• 2 timeouts → penalty (±6 runs)\n\n"
    "⚠️ <b>Restriction</b>\n"
    "• 0 is <b>NOT allowed</b> on hat-trick bowling"
)

HELP_TEAM_TEXT = (
    "👥 <b>Team Play Mode</b>\n\n"
    "Create teams &amp; play cricket with friends 🏏\n\n"
    "🚀 <b>Quick Start</b>\n"
    "1. /play in the group\n"
    "2. Pick <b>Team Mode</b>\n"
    "3. Tap <b>I'm the Host</b>\n"
    "4. /create_teams to open the lobby\n"
    "5. Players /join_teamA or /join_teamB\n"
    "6. /choose_cap → /set_overs → enjoy!\n\n"
    "📋 <b>Team Commands</b>\n"
    "/create_teams – open team lobby\n"
    "/join_teamA · /join_teamB – pick a side\n"
    "/teams – view current squads\n"
    "/changeside – swap teams\n"
    "/shiftteam – host moves a player\n"
    "/add · /remove – host roster edits\n"
    "/changehost – pass host to someone else\n"
    "/changecap – change captain\n"
    "/choose_cap – pick captains\n"
    "/set_overs – set match overs\n"
    "/batting · /bowling – choose first innings roles\n"
    "/score · /graph – live status\n"
    "/rejointeams – restore lobby after a glitch\n"
    "/restore – recover an interrupted match\n"
    "/endgame – end the match"
)

HELP_SOLO_TEXT = (
    "🧍 <b>Solo Mode</b>\n\n"
    "Free-for-all cricket — every player for themselves 🏏\n\n"
    "🚀 <b>Quick Start</b>\n"
    "1. /play in the group\n"
    "2. Pick <b>Solo Mode</b>\n"
    "3. Players /joingame to enter the lobby\n"
    "4. Wait for the timer or use /forcestart\n\n"
    "📋 <b>Solo Commands</b>\n"
    "/joingame – join the solo lobby\n"
    "/leavegame – leave before it starts\n"
    "/extend – add more time to the lobby\n"
    "/forcestart – host starts immediately\n"
    "/score – live scorecard\n"
    "/endgame – end the match\n\n"
    "🎯 <b>Rules</b>\n"
    "• Batters pick <b>1–6</b> (no zero)\n"
    "• Same pick as bowler = OUT\n"
    "• 2 timeouts in a row → -6 runs &amp; 20-min ban"
)

HELP_DUEL_TEXT = (
    "⚔️ <b>Duel Mode</b>\n\n"
    "Quick 1-vs-1 matches via DM matchmaking 🥊\n\n"
    "🚀 <b>Quick Start</b>\n"
    "1. DM the bot and send /duel\n"
    "2. You’ll be queued with another player\n"
    "3. Match starts automatically — play in DM\n\n"
    "📋 <b>Duel Commands</b>\n"
    "/duel – join the matchmaking queue (DM only)\n"
    "/score – live scorecard during the duel\n"
    "/endgame – forfeit / end the duel\n\n"
    "🎯 <b>Rules</b>\n"
    "• Best-of-overs head-to-head format\n"
    "• Batter &amp; bowler send 1–6 privately\n"
    "• Same number = OUT\n"
    "• Wins/losses count toward your duel rating"
)

HELP_USER_TEXT = (
    "👤 <b>User Commands</b>\n\n"
    "Track your stats, profile and progress 📈\n\n"
    "📊 <b>Profile &amp; Stats</b>\n"
    "/userinfo [user] – full profile (alias /profile, /userstats)\n"
    "/stats – global bot stats\n"
    "/user_ranks – leaderboard of top players\n"
    "/achievements – your unlocked achievements\n"
    "/compare <code>@user1 @user2</code> – compare two players\n"
    "/analyze [user] – AI-powered playstyle analysis\n\n"
    "💬 <b>Other</b>\n"
    "/start – open the main menu (in DM)\n"
    "/help – this help menu"
)

HELP_COMMANDS_TEXT = (
    "📋 <b>All Commands</b>\n\n"
    "🟢 <b>Basics</b>\n"
    "/start · /help · /play · /duel\n\n"
    "👥 <b>Team Mode</b>\n"
    "/create_teams · /join_teamA · /join_teamB\n"
    "/teams · /changeside · /shiftteam\n"
    "/add · /remove · /changehost · /changecap\n"
    "/choose_cap · /set_overs · /batting · /bowling\n"
    "/rejointeams · /restore · /endgame\n\n"
    "🧍 <b>Solo Mode</b>\n"
    "/joingame · /leavegame · /extend · /forcestart\n\n"
    "⚔️ <b>Duel Mode</b>\n"
    "/duel (DM)\n\n"
    "📊 <b>Live Match</b>\n"
    "/score · /graph · /endgame\n\n"
    "👤 <b>Profile &amp; Stats</b>\n"
    "/userinfo · /profile · /userstats · /stats\n"
    "/user_ranks · /achievements · /compare · /analyze"
)


@Client.on_message(filters.command("help"))
async def help_cmd(client, message):
    try:
        await add_user(message.from_user.id)
    except Exception:
        pass

    try:
        await message.reply_text(
            HELP_HOME_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=_home_keyboard(),
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^help_"))
async def help_callback(client, cb):
    pages = {
        "help_play": HELP_PLAY_TEXT,
        "help_team": HELP_TEAM_TEXT,
        "help_solo": HELP_SOLO_TEXT,
        "help_duel": HELP_DUEL_TEXT,
        "help_user": HELP_USER_TEXT,
        "help_commands": HELP_COMMANDS_TEXT,
    }

    try:
        data = cb.data

        if data == "help_back":
            text = HELP_HOME_TEXT
            buttons = _home_keyboard()
        elif data in pages:
            text = pages[data]
            buttons = _back_keyboard()
        else:
            return await cb.answer("Expired 😴", show_alert=True)

        await cb.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=buttons,
        )
        await cb.answer()

    except Exception:
        try:
            await cb.answer("Something glitched 😅", show_alert=True)
        except Exception:
            pass
