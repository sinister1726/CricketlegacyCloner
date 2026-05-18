import random
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database.users import add_user, total_users
from database.groups import total_groups

PLAYZONE_LINK = "https://t.me/CLG_fun_zone"
SUPPORT_LINK  = "https://t.me/Legacynewzz"

START_MOODS = [
    "🏏 𝗪𝗲𝗹𝗰𝗼𝗺𝗲, 𝗖𝗮𝗽𝘁𝗮𝗶𝗻!",
    "✨ 𝗥𝗲𝗮𝗱𝘆 𝘁𝗼 𝗯𝘂𝗶𝗹𝗱 𝘆𝗼𝘂𝗿 𝗰𝗿𝗶𝗰𝗸𝗲𝘁 𝗹𝗲𝗴𝗮𝗰𝘆?",
    "🔥 𝗧𝗵𝗲 𝗽𝗶𝘁𝗰𝗵 𝗶𝘀 𝘀𝗲𝘁. 𝗟𝗲𝘁'𝘀 𝗽𝗹𝗮𝘆!",
]

CLONE_MOODS = [
    "🏏 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 𝘁𝗼 𝘆𝗼𝘂𝗿 𝗖𝗿𝗶𝗰𝗸𝗲𝘁 𝗮𝗿𝗲𝗻𝗮!",
    "🔥 𝗟𝗲𝘁 𝘁𝗵𝗲 𝗴𝗮𝗺𝗲 𝗯𝗲𝗴𝗶𝗻!",
    "⚡ 𝗬𝗼𝘂𝗿 𝗰𝗿𝗶𝗰𝗸𝗲𝘁 𝗯𝗼𝘁 𝗶𝘀 𝗿𝗲𝗮𝗱𝘆!",
]

# Template variables available in custom start messages:
# {name}         → user's first name
# {mention}      → HTML mention of the user
# {username}     → @username  (or first name if no username)
# {id}           → user's Telegram ID
# {bot_name}     → this bot's display name
# {bot_username} → this bot's @username
# {users_count}  → total registered users in this bot
# {groups_count} → total registered groups in this bot
# {date}         → today's date  e.g. "18 May 2026"
# {time}         → current UTC time  e.g. "14:30"


async def _fill_template(text: str, user, me=None) -> str:
    """Replace all supported template vars in a custom start message."""
    if "{" not in text:
        return text

    mention  = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
    username = f"@{user.username}" if user.username else user.first_name

    bot_name     = me.first_name if me else "Cricket Bot"
    bot_username = f"@{me.username}" if (me and me.username) else ""

    uc = gc = "?"
    try:
        uc = str(await total_users())
    except Exception:
        pass
    try:
        gc = str(await total_groups())
    except Exception:
        pass

    now  = datetime.utcnow()
    date = now.strftime("%d %b %Y")
    time = now.strftime("%H:%M")

    return (
        text
        .replace("{name}",         user.first_name)
        .replace("{mention}",      mention)
        .replace("{username}",     username)
        .replace("{id}",           str(user.id))
        .replace("{bot_name}",     bot_name)
        .replace("{bot_username}", bot_username)
        .replace("{users_count}",  uc)
        .replace("{groups_count}", gc)
        .replace("{date}",         date)
        .replace("{time}",         time)
    )


async def _get_clone_start_config(owner_id: int) -> dict:
    try:
        from database.clone import get_all_clone_settings
        return await get_all_clone_settings(owner_id)
    except Exception:
        return {}


@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message):
    user       = message.from_user
    first_name = user.first_name or "Captain"

    is_new = await add_user(user.id, first_name)

    args = message.command[1] if len(message.command) > 1 else ""
    if args == "duel":
        from plugins.game.duel import get_duel_matchmaking_card
        text, buttons = get_duel_matchmaking_card()
        await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=buttons)
        return

    try:
        me = await client.get_me()
    except Exception:
        me = None

    # ── CLONE BOT START ───────────────────────────────────────────────────────
    if Config.IS_CLONE and Config.CLONE_OWNER_ID:
        s = await _get_clone_start_config(Config.CLONE_OWNER_ID)

        start_image   = s.get("start_image")   or Config.START_IMAGE
        support_link  = s.get("support_link")  or Config.MAIN_SUPPORT
        playzone_link = s.get("playzone_link") or PLAYZONE_LINK
        custom_text   = s.get("start_text")
        mood          = random.choice(CLONE_MOODS)

        if custom_text:
            caption = await _fill_template(custom_text, user, me)
        else:
            caption = (
                f"{mood}\n"
                "────┈┄┄╌╌╌╌┄┄┈────\n\n"
                f"👤 <b>{first_name}</b>, welcome! 🏏\n\n"
                f"🧬 <b>Clone of {Config.MAIN_BOT_USERNAME}</b>\n"
                "For your tournament and group\n\n"
                "🎮 Play epic team & solo matches\n"
                "⚔️ Challenge rivals in 1v1 Duel\n"
                "📊 Track your stats & achievements\n\n"
                "👇 Use the buttons below to get started"
            )

        add_btn_username = me.username if me else ""

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🏏 Play Zone",  url=playzone_link),
                InlineKeyboardButton("🆘 Support",    url=support_link),
            ],
            [
                InlineKeyboardButton(
                    "➕ Add to Group",
                    url=f"https://t.me/{add_btn_username}?startgroup=true",
                ) if add_btn_username else
                InlineKeyboardButton("➕ Add to Group", url=playzone_link),
            ],
        ])

    # ── MAIN BOT START ────────────────────────────────────────────────────────
    else:
        start_image = Config.START_IMAGE
        mood        = random.choice(START_MOODS)

        caption = (
            f"{mood}\n"
            "────┈┄┄╌╌╌╌┄┄┈────\n\n"
            f"👤 <b>{first_name}</b>, welcome to <b>Cricket Legacy</b> ✨\n\n"
            "🏏 <b>Cricket Legacy v2</b>\n\n"
            "🎮 Play epic team & solo matches\n"
            "⚔️ Challenge rivals in 1v1 Duel\n"
            "📊 Track stats & achievements\n"
            "🎙 Live match vibes & action\n\n"
            "🧬 <b>Want your own cricket bot?</b>\n"
            "Clone this bot for your group or tournament!\n\n"
            "👇 Use the buttons below"
        )

        bot_un = me.username if me else (Config.BOT_USERNAME.replace("@", ""))
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("ʟᴇɢᴀᴄʏ ᴘʟᴀʏᴢᴏɴᴇ 🏏", url=PLAYZONE_LINK),
                InlineKeyboardButton("🆘 ꜱᴜᴘᴘᴏʀᴛ",         url=SUPPORT_LINK),
            ],
            [
                InlineKeyboardButton(
                    "➕ ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ",
                    url=f"https://t.me/{bot_un}?startgroup=true",
                ),
            ],
            [
                InlineKeyboardButton("🧬 Get Your Clone Bot", callback_data="howclone"),
            ],
        ])

    try:
        await message.reply_photo(
            photo=start_image,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=buttons,
        )
    except Exception:
        await message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=buttons)

    if is_new:
        try:
            count = await total_users()
            log_text = (
                "✨ <b>NEW PLAYER JOINED</b>\n\n"
                f"👤 {first_name}\n"
                f"🆔 <code>{user.id}</code>\n"
                f"📊 Total Users: {count}"
            )
            if Config.IS_CLONE and Config.CLONE_OWNER_ID:
                s = await _get_clone_start_config(Config.CLONE_OWNER_ID)
                log_ch = s.get("log_channel")
                if log_ch:
                    try:
                        await client.send_message(
                            int(log_ch), log_text, parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass
            else:
                await client.send_message(Config.LOG_CHANNEL, log_text, parse_mode=ParseMode.HTML)
        except Exception:
            pass


@Client.on_message(filters.private & filters.text & ~filters.regex(r"^/"), group=1)
async def auto_register_user(client: Client, message):
    user = message.from_user
    if not user:
        return
    try:
        await add_user(user.id, user.first_name)
    except Exception:
        pass
