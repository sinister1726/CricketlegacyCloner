"""
Clone bot plugins:
  /panel     — Owner-only customisation panel (DM)
  /howclone  — Guide for users who want their own clone bot
"""

from config import Config

if not Config.IS_CLONE or not Config.CLONE_OWNER_ID:
    pass          # howclone callback is handled by clone_mgmt.py on the main bot
else:
    from pyrogram import Client, filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import (
        InlineKeyboardMarkup,
        InlineKeyboardButton,
        CallbackQuery,
        Message,
    )
    from database.clone import get_all_clone_settings, set_clone_setting

    _OWNER = Config.CLONE_OWNER_ID
    _MAIN  = Config.MAIN_BOT_USERNAME or "@CricketLegacy2Bot"
    _awaiting: dict[int, str] = {}

    # ── Settings ───────────────────────────────────────────────────────────────
    SETTING_LABELS = {
        "start_image":   "🖼  Start Image",
        "start_text":    "📝  Start Message",
        "support_link":  "🔗  Support Link",
        "playzone_link": "🎮  PlayZone Link",
        "log_channel":   "📡  Log Channel",
        "welcome_msg":   "👋  Group Welcome",
    }

    SETTING_PROMPTS = {
        "start_image": (
            "🖼 <b>Start Image URL</b>\n\n"
            "Send a direct image URL shown on /start.\n"
            "<i>Example: https://graph.org/file/abc.jpg</i>\n\n"
            "Send /cancel to abort."
        ),
        "start_text": (
            "📝 <b>Start Message</b>\n\n"
            "Send your custom /start text. HTML formatting supported.\n\n"
            "<b>Available variables:</b>\n"
            "<code>{name}</code> — first name\n"
            "<code>{mention}</code> — clickable mention\n"
            "<code>{username}</code> — @username\n"
            "<code>{id}</code> — Telegram ID\n"
            "<code>{bot_name}</code> — this bot's name\n"
            "<code>{bot_username}</code> — this bot's @username\n"
            "<code>{users_count}</code> — total users\n"
            "<code>{groups_count}</code> — total groups\n"
            "<code>{date}</code> — today's date\n"
            "<code>{time}</code> — current UTC time\n\n"
            "Send /cancel to abort."
        ),
        "support_link": (
            "🔗 <b>Support Group Link</b>\n\n"
            "Send your support group / channel link.\n"
            "<i>Example: https://t.me/yourgroup</i>\n\n"
            "Send /cancel to abort."
        ),
        "playzone_link": (
            "🎮 <b>PlayZone Link</b>\n\n"
            "Send your main cricket group or channel link.\n"
            "<i>Example: https://t.me/yourplayzone</i>\n\n"
            "Send /cancel to abort."
        ),
        "log_channel": (
            "📡 <b>Log Channel ID</b>\n\n"
            "Send the numeric ID of your log channel.\n"
            "The bot must be an admin there.\n"
            "<i>Example: -1001234567890</i>\n\n"
            "Send /cancel to abort."
        ),
        "welcome_msg": (
            "👋 <b>Group Welcome Message</b>\n\n"
            "Sent when your bot is added to a group. HTML supported.\n\n"
            "<b>Variables:</b>\n"
            "<code>{group}</code> — group name\n"
            "<code>{bot_name}</code> — this bot's name\n"
            "<code>{bot_username}</code> — this bot's @username\n\n"
            "<i>Example:\n"
            "🏏 Welcome to {group}!\n"
            "I'm {bot_name} — let's play cricket!\n"
            "Use /play to start a match.</i>\n\n"
            "Send /cancel to abort."
        ),
    }

    # ── Panel UI ───────────────────────────────────────────────────────────────
    def _panel_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🖼  Start Image",   callback_data="cp_set_start_image"),
                InlineKeyboardButton("📝  Start Message", callback_data="cp_set_start_text"),
            ],
            [
                InlineKeyboardButton("🔗  Support Link",  callback_data="cp_set_support_link"),
                InlineKeyboardButton("🎮  PlayZone",      callback_data="cp_set_playzone_link"),
            ],
            [
                InlineKeyboardButton("📡  Log Channel",   callback_data="cp_set_log_channel"),
                InlineKeyboardButton("👋  Welcome Msg",   callback_data="cp_set_welcome_msg"),
            ],
            [
                InlineKeyboardButton("📋  View Settings", callback_data="cp_view"),
                InlineKeyboardButton("🧬  How to Clone",  callback_data="howclone"),
            ],
            [
                InlineKeyboardButton("✖  Close",         callback_data="cp_close"),
            ],
        ])

    def _panel_caption(bot_username: str = "", owner_name: str = "") -> str:
        tag   = bot_username or "Your Clone"
        owner = owner_name   or "You"
        return (
            f"<b>⚙️  Clone Bot Panel</b>\n"
            f"<code>{'─' * 28}</code>\n"
            f"🤖  <b>Bot</b>    {tag}\n"
            f"👤  <b>Owner</b>  {owner}\n"
            f"<code>{'─' * 28}</code>\n\n"
            f"<b>🎨  Appearance</b>\n"
            f"    › Start Image  ·  Start Message\n\n"
            f"<b>🔗  Links</b>\n"
            f"    › Support  ·  PlayZone\n\n"
            f"<b>📡  Groups</b>\n"
            f"    › Log Channel  ·  Welcome Message\n\n"
            f"<i>Tap a button to update that setting.</i>"
        )

    def _view_caption(settings: dict) -> str:
        lines = [
            "<b>📋  Current Settings</b>",
            f"<code>{'─' * 28}</code>",
        ]
        for key, label in SETTING_LABELS.items():
            val = settings.get(key)
            if not val:
                display = "<i>default</i>"
            elif isinstance(val, str) and len(val) > 55:
                display = f"<code>{val[:55]}…</code>"
            else:
                display = f"<code>{val}</code>"
            lines.append(f"\n{label}\n  {display}")
        lines.append(f"\n<code>{'─' * 28}</code>")
        return "\n".join(lines)

    # ── /panel command ─────────────────────────────────────────────────────────
    @Client.on_message(filters.command("panel") & filters.private & filters.user(_OWNER))
    async def panel_cmd(client: Client, message: Message):
        _awaiting.pop(_OWNER, None)
        await _send_panel(client, message)

    async def _send_panel(client: Client, message: Message):
        me           = await client.get_me()
        bot_username = f"@{me.username}" if me.username else me.first_name

        try:
            user       = await client.get_users(_OWNER)
            owner_name = user.first_name or str(_OWNER)
        except Exception:
            owner_name = str(_OWNER)

        caption = _panel_caption(bot_username, owner_name)
        kb      = _panel_kb()

        try:
            from utils.panel_image import generate_panel_image
            img = generate_panel_image(bot_username=bot_username, owner_name=owner_name)
            await message.reply_photo(photo=img, caption=caption,
                                      parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            await message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=kb)

    # ── /howclone ──────────────────────────────────────────────────────────────
    @Client.on_message(filters.command("howclone"))
    async def howclone_cmd(client: Client, message: Message):
        _main_un = _MAIN.replace("@", "")
        await message.reply_text(
            f"🧬 <b>Get Your Own Cricket Bot</b>\n"
            f"<code>{'─' * 28}</code>\n\n"
            f"This bot is a clone of <b>{_MAIN}</b>.\n"
            f"You can get your own identical bot for your group!\n\n"
            f"<b>① Contact</b> <code>@Spideyyye</code> → pay ₹200/month\n"
            f"<b>② Create</b> a bot via @BotFather → copy the token\n"
            f"<b>③ Send</b> to <b>{_MAIN}</b>:\n"
            f"   <code>/clone &lt;your bot token&gt;</code>\n"
            f"<b>④ Open</b> your new bot → send <code>/panel</code>\n"
            f"<b>⑤ Add</b> it to your group → <code>/play</code> 🏏\n\n"
            f"<code>{'─' * 28}</code>\n"
            f"✅ Separate stats, users & groups\n"
            f"♻️ Stats saved — restart anytime\n"
            f"⏱ 28-day plan, renewable",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬  Contact @Spideyyye", url="https://t.me/Spideyyye")],
                [InlineKeyboardButton(f"🤖  Open {_MAIN}",     url=f"https://t.me/{_MAIN.replace('@','')}")],
            ]),
        )

    @Client.on_callback_query(filters.regex("^howclone$"))
    async def howclone_cb(client: Client, cb: CallbackQuery):
        await cb.answer()
        _main_un = _MAIN.replace("@", "")
        await cb.message.reply_text(
            f"🧬 <b>Get Your Own Cricket Bot</b>\n"
            f"<code>{'─' * 28}</code>\n\n"
            f"This bot is a clone of <b>{_MAIN}</b>.\n"
            f"Get your own identical bot for your group or tournament!\n\n"
            f"<b>① Contact</b> <code>@Spideyyye</code> → pay ₹200/month\n"
            f"<b>② Create</b> a bot via @BotFather → copy the token\n"
            f"<b>③ Send</b> to <b>{_MAIN}</b>:\n"
            f"   <code>/clone &lt;your bot token&gt;</code>\n"
            f"<b>④ Open</b> your new bot → send <code>/panel</code>\n"
            f"<b>⑤ Add</b> it to your group → <code>/play</code> 🏏\n\n"
            f"✅ Own stats  ·  ♻️ Saved on restart  ·  ⏱ 28 days",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬  Contact @Spideyyye", url="https://t.me/Spideyyye")],
                [InlineKeyboardButton(f"🤖  Open {_MAIN}",     url=f"https://t.me/{_MAIN.replace('@','')}")],
            ]),
        )

    # ── Panel callbacks ────────────────────────────────────────────────────────
    @Client.on_callback_query(filters.regex(r"^cp_set_\w+$") & filters.user(_OWNER))
    async def panel_set_cb(client: Client, cb: CallbackQuery):
        key = cb.data[len("cp_set_"):]
        if key not in SETTING_PROMPTS:
            return await cb.answer("Unknown setting.", show_alert=True)
        _awaiting[_OWNER] = key
        await cb.answer()
        await cb.message.reply_text(SETTING_PROMPTS[key], parse_mode=ParseMode.HTML)

    @Client.on_callback_query(filters.regex(r"^cp_view$") & filters.user(_OWNER))
    async def panel_view_cb(client: Client, cb: CallbackQuery):
        await cb.answer()
        settings = await get_all_clone_settings(_OWNER)
        await cb.message.reply_text(
            _view_caption(settings),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("‹  Back to Panel", callback_data="cp_back"),
            ]]),
        )

    @Client.on_callback_query(filters.regex(r"^cp_back$") & filters.user(_OWNER))
    async def panel_back_cb(client: Client, cb: CallbackQuery):
        await cb.answer()
        me           = await client.get_me()
        bot_username = f"@{me.username}" if me.username else me.first_name
        try:
            user       = await client.get_users(_OWNER)
            owner_name = user.first_name or str(_OWNER)
        except Exception:
            owner_name = str(_OWNER)

        caption = _panel_caption(bot_username, owner_name)
        kb      = _panel_kb()

        try:
            await cb.message.delete()
        except Exception:
            pass

        try:
            from utils.panel_image import generate_panel_image
            img = generate_panel_image(bot_username=bot_username, owner_name=owner_name)
            await cb.message.reply_photo(photo=img, caption=caption,
                                         parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            await cb.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=kb)

    @Client.on_callback_query(filters.regex(r"^cp_close$") & filters.user(_OWNER))
    async def panel_close_cb(client: Client, cb: CallbackQuery):
        _awaiting.pop(_OWNER, None)
        await cb.answer("Panel closed.")
        try:
            await cb.message.delete()
        except Exception:
            try:
                await cb.message.edit_caption("✖  Panel closed.")
            except Exception:
                pass

    # ── Text input handler ─────────────────────────────────────────────────────
    @Client.on_message(
        filters.private & filters.user(_OWNER)
        & ~filters.command(["panel", "start", "help", "howclone"]),
        group=5,
    )
    async def panel_input_handler(client: Client, message: Message):
        if _OWNER not in _awaiting:
            return

        key  = _awaiting.pop(_OWNER)
        text = (message.text or "").strip()

        if text.lower() == "/cancel":
            return await message.reply_text("❌ Cancelled.", reply_markup=_panel_kb())

        if not text:
            _awaiting[_OWNER] = key
            return await message.reply_text("⚠️ Please send a value or /cancel.")

        # Validation
        if key == "log_channel":
            try:
                text = str(int(text))
            except ValueError:
                _awaiting[_OWNER] = key
                return await message.reply_text(
                    "❌ Must be a number like <code>-1001234567890</code>.\nTry again or /cancel.",
                    parse_mode=ParseMode.HTML,
                )

        if key in ("support_link", "playzone_link", "start_image") and not text.startswith("http"):
            _awaiting[_OWNER] = key
            return await message.reply_text(
                "❌ Must be a valid URL starting with <code>https://</code>.\nTry again or /cancel.",
                parse_mode=ParseMode.HTML,
            )

        await set_clone_setting(_OWNER, key, text)
        label   = SETTING_LABELS.get(key, key)
        preview = text[:100] + ("…" if len(text) > 100 else "")

        await message.reply_text(
            f"✅ <b>{label}</b> updated!\n\n"
            f"<code>{preview}</code>\n\n"
            f"<i>Takes effect immediately.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=_panel_kb(),
        )
