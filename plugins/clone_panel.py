"""
Clone bot plugins:
  /panel     — Customisation panel (owner only, DM only)
  /howclone  — Guide for users who want their own clone
"""

from config import Config

if not Config.IS_CLONE or not Config.CLONE_OWNER_ID:
    # ── Stub: NOT a clone bot ──────────────────────────────────────────────────
    # The howclone callback is handled by clone_mgmt.py in the main bot.
    pass
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

    _OWNER  = Config.CLONE_OWNER_ID
    _MAIN   = Config.MAIN_BOT_USERNAME or "@CricketLegacy2Bot"
    _awaiting: dict[int, str] = {}

    # ── Settings registry ─────────────────────────────────────────────────────
    SETTING_LABELS = {
        "start_image":   "🖼 Start Image",
        "start_text":    "📝 Start Message",
        "support_link":  "🔗 Support Link",
        "playzone_link": "🎮 PlayZone Link",
        "log_channel":   "📢 Log Channel",
        "welcome_msg":   "👋 Group Welcome",
        "group_rules":   "📜 Group Rules",
        "bot_bio":       "📝 Bot Bio",
    }

    SETTING_PROMPTS = {
        "start_image": (
            "🖼 <b>Start Image URL</b>\n\n"
            "Send the direct image URL for your bot's /start photo.\n"
            "<i>Example: https://graph.org/file/abc123.jpg</i>\n\n"
            "Template vars: none (image URL only)\n\n"
            "Send /cancel to abort."
        ),
        "start_text": (
            "📝 <b>Start Message</b>\n\n"
            "Send your custom start message. HTML formatting supported.\n\n"
            "<b>Template variables:</b>\n"
            "<code>{name}</code> — user's first name\n"
            "<code>{mention}</code> — clickable mention\n"
            "<code>{username}</code> — @username\n"
            "<code>{id}</code> — user's Telegram ID\n"
            "<code>{bot_name}</code> — this bot's name\n"
            "<code>{bot_username}</code> — this bot's @username\n"
            "<code>{users_count}</code> — total users in this bot\n"
            "<code>{groups_count}</code> — total groups this bot is in\n"
            "<code>{date}</code> — today's date\n"
            "<code>{time}</code> — current UTC time\n\n"
            "Send /cancel to abort."
        ),
        "support_link": (
            "🔗 <b>Support Group Link</b>\n\n"
            "Send your support group invite link.\n"
            "<i>Example: https://t.me/yourgroup</i>\n\n"
            "Send /cancel to abort."
        ),
        "playzone_link": (
            "🎮 <b>PlayZone / Main Group Link</b>\n\n"
            "Send your main cricket group link.\n"
            "<i>Example: https://t.me/yourplayzone</i>\n\n"
            "Send /cancel to abort."
        ),
        "log_channel": (
            "📢 <b>Log Channel ID</b>\n\n"
            "Send the chat ID of your log channel (must be a number).\n"
            "The bot must be an admin in that channel.\n"
            "<i>Example: -1001234567890</i>\n\n"
            "Send /cancel to abort."
        ),
        "welcome_msg": (
            "👋 <b>Group Welcome Message</b>\n\n"
            "Send the message your bot will post when it's added to a group.\n"
            "HTML formatting supported.\n\n"
            "<b>Template variables:</b>\n"
            "<code>{group}</code> — group name\n"
            "<code>{bot_name}</code> — this bot's name\n"
            "<code>{bot_username}</code> — this bot's @username\n\n"
            "<i>Example:</i>\n"
            "<i>🏏 Hello {group}! I'm ready to host cricket matches.\n"
            "Use /play to start a game!</i>\n\n"
            "Send /cancel to abort."
        ),
        "group_rules": (
            "📜 <b>Group Rules Message</b>\n\n"
            "Send the rules message for your groups (shown with /rules command).\n"
            "HTML formatting supported.\n\n"
            "<i>Example:</i>\n"
            "<i>📜 Rules:\n1. No spamming\n2. Respect all players\n3. Have fun! 🏏</i>\n\n"
            "Send /cancel to abort."
        ),
        "bot_bio": (
            "📝 <b>Bot Bio / Description</b>\n\n"
            "Send a short description for your bot.\n"
            "This will be shown in /about and your bot's profile.\n\n"
            "Max 120 characters.\n\n"
            "Send /cancel to abort."
        ),
    }

    # ── Panel keyboard ────────────────────────────────────────────────────────
    def _panel_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🖼 Start Image",   callback_data="cp_set_start_image"),
                InlineKeyboardButton("📝 Start Message", callback_data="cp_set_start_text"),
            ],
            [
                InlineKeyboardButton("🔗 Support Link",  callback_data="cp_set_support_link"),
                InlineKeyboardButton("🎮 PlayZone Link", callback_data="cp_set_playzone_link"),
            ],
            [
                InlineKeyboardButton("📢 Log Channel",   callback_data="cp_set_log_channel"),
                InlineKeyboardButton("👋 Group Welcome", callback_data="cp_set_welcome_msg"),
            ],
            [
                InlineKeyboardButton("📜 Group Rules",   callback_data="cp_set_group_rules"),
                InlineKeyboardButton("📝 Bot Bio",       callback_data="cp_set_bot_bio"),
            ],
            [
                InlineKeyboardButton("📋 View Settings", callback_data="cp_view"),
                InlineKeyboardButton("🔄 Refresh Panel", callback_data="cp_back"),
            ],
            [
                InlineKeyboardButton("✖ Close Panel",   callback_data="cp_close"),
            ],
        ])

    def _panel_caption(bot_username: str = "", owner_name: str = "") -> str:
        return (
            f"⚙️ <b>CLONE BOT PANEL</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>Bot:</b> {bot_username or 'Your Clone'}\n"
            f"👤 <b>Owner:</b> {owner_name or 'You'}\n\n"
            f"<b>Appearance</b>\n"
            f"🖼 Start Image  •  📝 Start Message\n\n"
            f"<b>Links</b>\n"
            f"🔗 Support  •  🎮 PlayZone\n\n"
            f"<b>Group Setup</b>\n"
            f"📢 Log Channel  •  👋 Group Welcome\n"
            f"📜 Group Rules  •  📝 Bot Bio\n\n"
            f"Tap any button to update that setting.\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )

    # ── /panel ────────────────────────────────────────────────────────────────
    @Client.on_message(filters.command("panel") & filters.private & filters.user(_OWNER))
    async def panel_cmd(client: Client, message: Message):
        _awaiting.pop(_OWNER, None)
        await _send_panel(client, message)

    async def _send_panel(client: Client, message: Message):
        try:
            me           = await client.get_me()
            bot_username = f"@{me.username}" if me.username else ""
            try:
                owner      = await client.get_users(_OWNER)
                owner_name = owner.first_name or str(_OWNER)
            except Exception:
                owner_name = str(_OWNER)

            from utils.panel_image import generate_panel_image
            img_buf = generate_panel_image(bot_username=bot_username, owner_name=owner_name)

            await message.reply_photo(
                photo=img_buf,
                caption=_panel_caption(bot_username, owner_name),
                parse_mode=ParseMode.HTML,
                reply_markup=_panel_kb(),
            )
        except Exception:
            await message.reply_text(
                _panel_caption(),
                parse_mode=ParseMode.HTML,
                reply_markup=_panel_kb(),
            )

    # ── /howclone — shown to regular users in clone bots ─────────────────────
    @Client.on_message(filters.command("howclone"))
    async def howclone_cmd(client: Client, message: Message):
        main_bot_un = _MAIN.replace("@", "")
        await message.reply_text(
            f"🧬 <b>Want Your Own Cricket Bot Like This?</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"This bot is a clone of <b>{_MAIN}</b>.\n"
            f"You can get your own identical bot for your tournament or group!\n\n"
            f"<b>Step 1 —</b> Contact <b>@Spideyyye</b> and pay ₹200/month\n"
            f"<b>Step 2 —</b> Create a new bot via @BotFather, copy the token\n"
            f"<b>Step 3 —</b> DM <b>{_MAIN}</b> and send:\n"
            f"<code>/clone &lt;your bot token&gt;</code>\n"
            f"<b>Step 4 —</b> DM your new bot, send /panel to customise it\n"
            f"<b>Step 5 —</b> Add it to your group and play! 🏏\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Fully separate stats, users & groups\n"
            f"♻️ Stats are saved — restart anytime with same token\n"
            f"⏱ 28-day plan, renewable",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Contact @Spideyyye",   url="https://t.me/Spideyyye")],
                [InlineKeyboardButton(f"🤖 Go to {_MAIN}", url=f"https://t.me/{main_bot_un}")],
            ]),
        )

    @Client.on_callback_query(filters.regex("^howclone$"))
    async def howclone_cb(client: Client, cb: CallbackQuery):
        await cb.answer()
        main_bot_un = _MAIN.replace("@", "")
        await cb.message.reply_text(
            f"🧬 <b>Want Your Own Cricket Bot Like This?</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"This bot is a clone of <b>{_MAIN}</b>.\n"
            f"You can get your own identical bot for your group!\n\n"
            f"<b>Step 1 —</b> Contact <b>@Spideyyye</b> and pay ₹200/month\n"
            f"<b>Step 2 —</b> Create a bot via @BotFather, copy the token\n"
            f"<b>Step 3 —</b> DM <b>{_MAIN}</b> → send <code>/clone &lt;token&gt;</code>\n"
            f"<b>Step 4 —</b> DM your bot, send /panel to customise\n"
            f"<b>Step 5 —</b> Add to your group and play! 🏏\n\n"
            f"✅ Fully separate stats  •  ♻️ Stats saved on restart\n"
            f"⏱ 28 days, renewable",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Contact @Spideyyye",   url="https://t.me/Spideyyye")],
                [InlineKeyboardButton(f"🤖 Go to {_MAIN}", url=f"https://t.me/{main_bot_un}")],
            ]),
        )

    # ── Panel callbacks ───────────────────────────────────────────────────────
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
        s     = await get_all_clone_settings(_OWNER)
        lines = ["📋 <b>CURRENT CLONE SETTINGS</b>\n━━━━━━━━━━━━━━━━━━━━━"]
        for key, label in SETTING_LABELS.items():
            val = s.get(key, "<i>not set</i>")
            if isinstance(val, str) and len(val) > 60:
                val = val[:60] + "…"
            lines.append(f"\n{label}:\n<code>{val}</code>")
        lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
        await cb.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Panel", callback_data="cp_back"),
            ]]),
        )

    @Client.on_callback_query(filters.regex(r"^cp_back$") & filters.user(_OWNER))
    async def panel_back_cb(client: Client, cb: CallbackQuery):
        await cb.answer()
        try:
            me           = await client.get_me()
            bot_username = f"@{me.username}" if me.username else ""
            try:
                owner      = await client.get_users(_OWNER)
                owner_name = owner.first_name or str(_OWNER)
            except Exception:
                owner_name = str(_OWNER)

            from utils.panel_image import generate_panel_image
            img_buf = generate_panel_image(bot_username=bot_username, owner_name=owner_name)

            try:
                await cb.message.delete()
            except Exception:
                pass
            await cb.message.reply_photo(
                photo=img_buf,
                caption=_panel_caption(bot_username, owner_name),
                parse_mode=ParseMode.HTML,
                reply_markup=_panel_kb(),
            )
        except Exception:
            try:
                await cb.message.edit_text(
                    _panel_caption(),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_panel_kb(),
                )
            except Exception:
                pass

    @Client.on_callback_query(filters.regex(r"^cp_close$") & filters.user(_OWNER))
    async def panel_close_cb(client: Client, cb: CallbackQuery):
        _awaiting.pop(_OWNER, None)
        try:
            await cb.message.delete()
        except Exception:
            await cb.message.edit_caption("✖ Panel closed.")
        await cb.answer("Panel closed.")

    # ── Panel input handler ───────────────────────────────────────────────────
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
            return await message.reply_text(
                "❌ Cancelled. No changes made.",
                reply_markup=_panel_kb(),
            )

        if not text:
            _awaiting[_OWNER] = key
            return await message.reply_text("⚠️ Please send a value, or /cancel to abort.")

        # Validation
        if key == "log_channel":
            try:
                text = str(int(text))
            except ValueError:
                _awaiting[_OWNER] = key
                return await message.reply_text(
                    "❌ Log channel must be a number (e.g. <code>-1001234567890</code>).\n"
                    "Try again or send /cancel.",
                    parse_mode=ParseMode.HTML,
                )

        if key in ("support_link", "playzone_link", "start_image") and not text.startswith("http"):
            _awaiting[_OWNER] = key
            return await message.reply_text(
                "❌ Please send a valid URL starting with <code>https://</code>.\n"
                "Try again or send /cancel.",
                parse_mode=ParseMode.HTML,
            )

        if key == "bot_bio" and len(text) > 120:
            text = text[:120]

        await set_clone_setting(_OWNER, key, text)
        label   = SETTING_LABELS.get(key, key)
        preview = text[:120] + ("…" if len(text) > 120 else "")

        await message.reply_text(
            f"✅ <b>{label} updated!</b>\n\n"
            f"<code>{preview}</code>\n\n"
            f"Changes take effect immediately.",
            parse_mode=ParseMode.HTML,
            reply_markup=_panel_kb(),
        )
