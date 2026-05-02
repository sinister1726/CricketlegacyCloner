from pyrogram import Client
from pyrogram.types import ChatMemberUpdated
from pyrogram.errors import ChatAdminRequired, ChatWriteForbidden
from database.groups import add_group, total_groups
from config import Config


@Client.on_chat_member_updated()
async def chat_member_handler(client: Client, update: ChatMemberUpdated):
    try:
        chat = update.chat
        old = update.old_chat_member
        new = update.new_chat_member

        if not old or not new:
            return

        if not new.user or not new.user.is_self:
            return

        inviter = update.from_user

        try:
            is_new_group = await add_group(chat.id, chat.title or "Unknown")
        except Exception:
            is_new_group = False

        try:
            await client.send_message(
                chat.id,
                "🏏 **Cricket Arena is now active!**\n\n"
                "• Start solo or team matches\n"
                "• Live commentary & stats\n"
                "• Competitive cricket fun\n\n"
                f"📢 Updates: {Config.PLAY_ZONE_INFO}"
            )
        except ChatWriteForbidden:
            pass
        except Exception:
            pass

        if inviter:
            try:
                await client.send_message(
                    inviter.id,
                    "✅ **Thanks for adding Cricket Arena!**\n\n"
                    "You can now start matches directly in your group.\n"
                    f"📢 Updates: {Config.PLAY_ZONE_INFO}"
                )
            except Exception:
                pass

        invite_link = "Not available"
        try:
            invite_link = await client.export_chat_invite_link(chat.id)
        except ChatAdminRequired:
            pass
        except Exception:
            pass

        if is_new_group:
            try:
                groups_count = await total_groups()
            except Exception:
                groups_count = "N/A"

            log_text = (
                "➕ **New Group Added**\n\n"
                f"📌 Group: {chat.title}\n"
                f"🆔 Chat ID: `{chat.id}`\n"
                f"👤 Added by: {inviter.first_name if inviter else 'Unknown'}\n"
                f"👤 User ID: `{inviter.id if inviter else 'N/A'}`\n"
                f"🔗 Invite: {invite_link}\n\n"
                f"📊 Total Groups: {groups_count}"
            )

            try:
                await client.send_message(Config.LOG_CHANNEL, log_text)
            except Exception:
                pass

    except Exception:
        pass
