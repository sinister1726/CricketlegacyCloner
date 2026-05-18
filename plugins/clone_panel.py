"""
/panel — Clone bot customisation panel (button-only UI).
Only accessible by the clone's owner (CLONE_OWNER_ID).
Only loaded when IS_CLONE=True.
"""

from config import Config

if not Config.IS_CLONE:
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

    _OWNER = Config.CLONE_OWNER_ID
    _awaiting: dict[int, str] = {}

    SETTING_LABELS = {
        "start_image":   "🖼 Start Image",
        "start_text":    "📝 Start Message",
        "support_link":  "🔗 Support Link",
        "playzone_link": "🎮 PlayZone Link",
        "log_channel":   "📢 Log Channel",
    }

    SETTING_PROMPTS = {
        "start_image":   "Send me the <b>image URL</b> for the start photo:\n\n<i>Example: https://graph.org/file/...</i>",
        "start_text":    "Send me the <b>start message text</b>.\nYou can use HTML formatting.\n\n<i>Keep it under 1000 characters.</i>",
        "support_link":  "Send me the <b>support group link</b>:\n\n<i>Example: https://t.me/yourgroup</i>",
        "playzone_link": "Send me the <b>PlayZone / main group link</b>:\n\n<i>Example: https://t.me/yourplayzone</i>",
        "log_channel":   "Send me the <b>log channel ID</b> (must be a number):\n\n<i>Example: -1001234567890</i>\n\nThe bot must be an admin in that channel.",
    }

    def _panel_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🖼 Start Image",    callback_data="cp_set_start_image"),
                InlineKeyboardButton("📝 Start Message",  callback_data="cp_set_start_text"),
            ],
            [
                InlineKeyboardButton("🔗 Support Link",   callback_data="cp_set_support_link"),
                InlineKeyboardButton("🎮 PlayZone Link",  callback_data="cp_set_playzone_link"),
            ],
            [
                InlineKeyboardButton("📢 Log Channel",    callback_data="cp_set_log_channel"),
            ],
            [
                InlineKeyboardButton("📋 View Settings",  callback_data="cp_view"),
                InlineKeyboardButton("✖ Close",           callback_data="cp_close"),
            ],
        ])

    def _panel_text() -> str:
        return (
            "⚙️ <b>CLONE BOT PANEL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Tap a button to change that setting.\n"
            "The bot will ask you to send the new value.\n\n"
            "🖼 <b>Start Image</b> — photo shown on /start\n"
            "📝 <b>Start Message</b> — text shown on /start\n"
            "🔗 <b>Support Link</b> — your support group\n"
            "🎮 <b>PlayZone Link</b> — your main play group\n"
            "📢 <b>Log Channel</b> — where bot logs go\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        )

    @Client.on_message(filters.command("panel") & filters.private & filters.user(_OWNER))
    async def panel_cmd(client: Client, message: Message):
        _awaiting.pop(_OWNER, None)
        await message.reply_text(
            _panel_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=_panel_kb(),
        )

    @Client.on_callback_query(filters.regex(r"^cp_set_\w+$") & filters.user(_OWNER))
    async def panel_set_cb(client: Client, cb: CallbackQuery):
        key = cb.data[len("cp_set_"):]
        if key not in SETTING_PROMPTS:
            return await cb.answer("Unknown setting.", show_alert=True)

        _awaiting[_OWNER] = key
        await cb.answer()
        await cb.message.reply_text(
            f"✏️ <b>{SETTING_LABELS[key]}</b>\n\n"
            + SETTING_PROMPTS[key]
            + "\n\n<i>Send /cancel to abort.</i>",
            parse_mode=ParseMode.HTML,
        )

    @Client.on_callback_query(filters.regex(r"^cp_view$") & filters.user(_OWNER))
    async def panel_view_cb(client: Client, cb: CallbackQuery):
        await cb.answer()
        s = await get_all_clone_settings(_OWNER)
        lines = ["📋 <b>CURRENT CLONE SETTINGS</b>\n━━━━━━━━━━━━━━━━━━━━━"]
        for key, label in SETTING_LABELS.items():
            val = s.get(key, "<i>not set — using default</i>")
            if key == "start_text" and val != "<i>not set — using default</i>":
                val = val[:60] + "…" if len(str(val)) > 60 else val
            lines.append(f"{label}:\n<code>{val}</code>")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        await cb.message.reply_text(
            "\n\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Panel", callback_data="cp_back")
            ]]),
        )

    @Client.on_callback_query(filters.regex(r"^cp_back$") & filters.user(_OWNER))
    async def panel_back_cb(client: Client, cb: CallbackQuery):
        await cb.answer()
        try:
            await cb.message.edit_text(
                _panel_text(),
                parse_mode=ParseMode.HTML,
                reply_markup=_panel_kb(),
            )
        except Exception:
            await cb.message.reply_text(
                _panel_text(),
                parse_mode=ParseMode.HTML,
                reply_markup=_panel_kb(),
            )

    @Client.on_callback_query(filters.regex(r"^cp_close$") & filters.user(_OWNER))
    async def panel_close_cb(client: Client, cb: CallbackQuery):
        _awaiting.pop(_OWNER, None)
        try:
            await cb.message.delete()
        except Exception:
            await cb.message.edit_text("✖ Panel closed.")
        await cb.answer()

    @Client.on_message(
        filters.private & filters.user(_OWNER) & ~filters.command(["panel", "start", "help"]),
        group=5,
    )
    async def panel_input_handler(client: Client, message: Message):
        if _OWNER not in _awaiting:
            return

        key = _awaiting.pop(_OWNER)
        text = (message.text or "").strip()

        if text.lower() == "/cancel":
            return await message.reply_text("❌ Cancelled. No changes made.")

        if not text:
            _awaiting[_OWNER] = key
            return await message.reply_text("⚠️ Please send a value, or /cancel to abort.")

        if key == "log_channel":
            try:
                text = str(int(text))
            except ValueError:
                _awaiting[_OWNER] = key
                return await message.reply_text(
                    "❌ Log channel must be a <b>number</b> (e.g. <code>-1001234567890</code>).\n"
                    "Try again or send /cancel.",
                    parse_mode=ParseMode.HTML,
                )

        if key in ("support_link", "playzone_link") and not text.startswith("http"):
            _awaiting[_OWNER] = key
            return await message.reply_text(
                "❌ Please send a valid URL starting with <code>https://</code>.\n"
                "Try again or send /cancel.",
                parse_mode=ParseMode.HTML,
            )

        await set_clone_setting(_OWNER, key, text)
        label = SETTING_LABELS.get(key, key)
        await message.reply_text(
            f"✅ <b>{label}</b> updated!\n\n"
            f"<code>{text[:200]}</code>\n\n"
            "Changes take effect on the next /start.",
            parse_mode=ParseMode.HTML,
            reply_markup=_panel_kb(),
        )
