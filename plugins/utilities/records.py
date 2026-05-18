"""
/records — Disabled. Group records and venue ranking have been removed.
"""

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.enums import ParseMode


_DISABLED_MSG = (
    "🚫 <b>Group Records Disabled</b>\n\n"
    "The /records feature has been removed from this bot.\n"
    "Use /stats and /leaderboard to view player stats."
)


@Client.on_message(filters.command("records") & filters.group)
async def records_cmd(client: Client, message: Message):
    await message.reply_text(_DISABLED_MSG, parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^rec_p_[12]$"))
async def records_page_cb(client: Client, query: CallbackQuery):
    await query.answer("Records feature has been removed.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^rec_noop$"))
async def records_noop_cb(client: Client, query: CallbackQuery):
    await query.answer()
