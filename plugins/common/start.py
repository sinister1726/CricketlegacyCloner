import random
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database.users import add_user, total_users

PLAYZONE_LINK = "https://t.me/CLG_fun_zone"
SUPPORT_LINK = "https://t.me/Legacynewzz"

START_MOODS = [
    "🏏 𝗪𝗲𝗹𝗰𝗼𝗺𝗲, 𝗖𝗮𝗽𝘁𝗮𝗶𝗻!",
    "✨ 𝗥𝗲𝗮𝗱𝘆 𝘁𝗼 𝗯𝘂𝗶𝗹𝗱 𝘆𝗼𝘂𝗿 𝗰𝗿𝗶𝗰𝗸𝗲𝘁 𝗹𝗲𝗴𝗮𝗰𝘆?",
    "🔥 𝗧𝗵𝗲 𝗽𝗶𝘁𝗰𝗵 𝗶𝘀 𝘀𝗲𝘁. 𝗟𝗲𝘁'𝘀 𝗽𝗹𝗮𝘆!",
]


async def _get_clone_start_config(owner_id: int) -> dict:
    """Fetch custom start settings for a clone bot."""
    try:
        from database.clone import get_all_clone_settings
        return await get_all_clone_settings(owner_id)
    except Exception:
        return {}


@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message):
    user = message.from_user
    first_name = user.first_name or "Captain"

    is_new = await add_user(user.id, first_name)

    args = message.command[1] if len(message.command) > 1 else ""
    if args == "duel":
        from plugins.game.duel import get_duel_matchmaking_card
        text, buttons = get_duel_matchmaking_card()
        await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=buttons)
        return

    mood = random.choice(START_MOODS)

    if Config.IS_CLONE and Config.CLONE_OWNER_ID:
        s = await _get_clone_start_config(Config.CLONE_OWNER_ID)
        start_image   = s.get("start_image")   or Config.START_IMAGE
        support_link  = s.get("support_link")  or Config.MAIN_SUPPORT
        playzone_link = s.get("playzone_link") or PLAYZONE_LINK
        custom_text   = s.get("start_text")

        if custom_text:
            caption = custom_text.replace("{name}", first_name)
        else:
            caption = (
                f"{mood}\n"
                "────┈┄┄╌╌╌╌┄┄┈────\n\n"
                f"👤 <b>{first_name}</b>, welcome! 🏏\n\n"
                "🎮 Play epic team & solo matches\n"
                "⚔️ Challenge rivals in 1v1 Duel\n"
                "📊 Track stats & achievements\n\n"
                f"🧬 <i>Powered by {Config.MAIN_BOT_USERNAME}</i>\n\n"
                "👇 Use the buttons below"
            )

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🏏 PlayZone", url=playzone_link),
                InlineKeyboardButton("🆘 Support",  url=support_link),
            ],
            [
                InlineKeyboardButton(
                    "➕ Add to Group",
                    url=f"https://t.me/{Config.BOT_USERNAME.replace('@', '')}?startgroup=true"
                )
            ],
        ])
    else:
        start_image   = Config.START_IMAGE
        support_link  = SUPPORT_LINK
        playzone_link = PLAYZONE_LINK

        caption = (
            f"{mood}\n"
            "────┈┄┄╌╌╌╌┄┄┈────\n\n"
            f"👤 <b>{first_name}</b>, welcome to <b>Cricket Legacy</b> ✨\n\n"
            "🏏 <b>Cricket Legacy v2</b>\n\n"
            "🎮 Play epic team & solo matches\n"
            "⚔️ Challenge rivals in 1v1 Duel\n"
            "📊 Track stats & achievements\n"
            "🎙 Live match vibes & action\n\n"
            "🐞 Found a bug?\n"
            "Report it in <b>PlayZone</b>\n\n"
            "👇 Use the buttons below"
        )

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("ʟᴇɢᴀᴄʏ ᴘʟᴀʏᴢᴏɴᴇ 🏏", url=PLAYZONE_LINK),
                InlineKeyboardButton("🆘 ꜱᴜᴘᴘᴏʀᴛ", url=SUPPORT_LINK),
            ],
            [
                InlineKeyboardButton("➕ ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ", url=f"https://t.me/{Config.BOT_USERNAME.replace('@','')}?startgroup=true")
            ],
        ])

    try:
        await message.reply_photo(
            photo=start_image,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=buttons
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
                        await client.send_message(int(log_ch), log_text, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass
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
