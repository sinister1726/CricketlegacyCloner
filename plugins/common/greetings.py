from pyrogram import Client
from pyrogram.types import ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import ChatAdminRequired, ChatWriteForbidden
from database.groups import add_group, total_groups
from config import Config


@Client.on_chat_member_updated()
async def chat_member_handler(client: Client, update: ChatMemberUpdated):
    try:
        chat = update.chat
        old  = update.old_chat_member
        new  = update.new_chat_member

        if not old or not new:
            return
        if not new.user or not new.user.is_self:
            return

        inviter = update.from_user

        # ── Main bot: only owner can add it to groups ─────────────────────────
        if not Config.IS_CLONE:
            inviter_id = inviter.id if inviter else None
            if inviter_id not in Config.OWNER_IDS:
                try:
                    await client.send_message(
                        chat.id,
                        "⚠️ <b>Sorry, I can't be added to groups by regular users.</b>\n\n"
                        "This is the main <b>Cricket Legacy</b> bot.\n"
                        "If you want your own cricket bot for your group or tournament, "
                        f"contact <b>@Spideyyye</b> to get a clone — ₹200/month.\n\n"
                        "👋 Leaving now…",
                        parse_mode="html",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(
                                "🧬 Get Your Own Cricket Bot",
                                url="https://t.me/Spideyyye",
                            )
                        ]]),
                    )
                except Exception:
                    pass
                try:
                    await client.leave_chat(chat.id)
                except Exception:
                    pass

                # DM the inviter about clone option
                if inviter_id:
                    try:
                        await client.send_message(
                            inviter_id,
                            "👋 <b>Hi!</b> I left that group.\n\n"
                            "The main bot can't be added to groups — but you can get your "
                            "<b>own private clone</b> of this bot for your tournament!\n\n"
                            "💬 Contact <b>@Spideyyye</b> — ₹200/month\n"
                            "Your bot, your groups, your stats.",
                            parse_mode="html",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton(
                                    "💬 Contact @Spideyyye",
                                    url="https://t.me/Spideyyye",
                                ),
                                InlineKeyboardButton(
                                    "❓ How to Clone?",
                                    url=f"https://t.me/{Config.BOT_USERNAME.replace('@', '')}?start=clone_info",
                                ),
                            ]]),
                        )
                    except Exception:
                        pass
                return

        # ── Clone bot OR owner adding main bot — proceed normally ─────────────
        try:
            is_new_group = await add_group(chat.id, chat.title or "Unknown")
        except Exception:
            is_new_group = False

        # Determine welcome message
        welcome_text = None
        if Config.IS_CLONE and Config.CLONE_OWNER_ID:
            try:
                from database.clone import get_clone_setting
                welcome_text = await get_clone_setting(Config.CLONE_OWNER_ID, "welcome_msg")
            except Exception:
                pass

        if not welcome_text:
            # Default welcome
            if Config.IS_CLONE:
                main_bot = Config.MAIN_BOT_USERNAME or "@CricketLegacy2Bot"
                welcome_text = (
                    f"🏏 <b>Cricket Arena is now active!</b>\n\n"
                    f"Play team & solo matches, challenge rivals in 1v1 Duel, "
                    f"track your stats and climb the leaderboard!\n\n"
                    f"🧬 Powered by {main_bot}\n"
                    f"Use /play to start a match!"
                )
            else:
                welcome_text = (
                    "🏏 <b>Cricket Arena is now active!</b>\n\n"
                    "• Start solo or team matches\n"
                    "• Live commentary & stats\n"
                    "• Competitive cricket fun\n\n"
                    f"📢 Updates: {Config.PLAY_ZONE_INFO}"
                )

        try:
            await client.send_message(chat.id, welcome_text, parse_mode="html")
        except ChatWriteForbidden:
            pass
        except Exception:
            pass

        if inviter:
            try:
                await client.send_message(
                    inviter.id,
                    "✅ <b>Thanks for adding the bot!</b>\n\n"
                    "You can now start matches directly in your group.\n"
                    "Use /play in the group to get going! 🏏",
                    parse_mode="html",
                )
            except Exception:
                pass

        if is_new_group:
            invite_link = "Not available"
            try:
                invite_link = await client.export_chat_invite_link(chat.id)
            except ChatAdminRequired:
                pass
            except Exception:
                pass

            try:
                groups_count = await total_groups()
            except Exception:
                groups_count = "N/A"

            log_text = (
                f"➕ <b>New Group Added</b>\n\n"
                f"📌 Group: {chat.title}\n"
                f"🆔 Chat ID: <code>{chat.id}</code>\n"
                f"👤 Added by: {inviter.first_name if inviter else 'Unknown'}\n"
                f"👤 User ID: <code>{inviter.id if inviter else 'N/A'}</code>\n"
                f"🔗 Invite: {invite_link}\n\n"
                f"📊 Total Groups: {groups_count}"
            )

            log_ch = Config.LOG_CHANNEL
            if Config.IS_CLONE and Config.CLONE_OWNER_ID:
                try:
                    from database.clone import get_clone_setting
                    custom_log = await get_clone_setting(Config.CLONE_OWNER_ID, "log_channel")
                    if custom_log:
                        log_ch = int(custom_log)
                except Exception:
                    pass

            try:
                await client.send_message(log_ch, log_text, parse_mode="html")
            except Exception:
                pass

    except Exception:
        pass
