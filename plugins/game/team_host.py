from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from pyrogram.enums import ParseMode

from Assets.files import TEAM_CREATE_IMAGE
from database.games import get_active_game, create_game, user_in_other_game
from utils.mentions import mention_html
from plugins.utilities.logger import send_match_log
@Client.on_callback_query(filters.regex("^mode_team$"))
async def team_mode_selected(client, query):
    await query.answer()

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👑 I'm Host",
                    callback_data="host_select"
                )
            ],
            [
                InlineKeyboardButton("🔙 Back", callback_data="mode_back"),
                InlineKeyboardButton("✖ Cancel", callback_data="mode_cancel")
            ]
        ]
    )

    await query.message.edit_media(
        media=InputMediaPhoto(
            media=TEAM_CREATE_IMAGE,
            caption=(
                "👑 <b>HOST SELECTION</b>\n\n"
                "Anyone can volunteer as host.\n"
                "<i>The host controls team setup.</i>"
            ),
            parse_mode=ParseMode.HTML
        ),
        reply_markup=buttons
    )

@Client.on_callback_query(filters.regex("^host_select$"))
async def confirm_host(client, query):
    user = query.from_user
    chat_id = query.message.chat.id
    group_title = query.message.chat.title or "Private Match"

    # Check if game already active
    existing = await get_active_game(chat_id)
    if existing:
        return await query.answer(
            "👑 Host already chosen.\nEnjoy the game 😌",
            show_alert=True
        )

    # Check if user already in another game
    other_game = await user_in_other_game(user.id, chat_id)
    if other_game:
        return await query.answer(
            f"⚠️ You are already playing in {other_game['title']}",
            show_alert=True
        )

    # Create game (returns game_id / UUID)
    game_id = await create_game(
        chat_id=chat_id,
        mode="team",
        host_id=user.id,
        title=group_title
    )

    # Build match object for logger
    match = {
        "game_id": str(game_id),
        "chat_id": chat_id,
        "host_name": user.mention
    }

    # Send match start log
    await send_match_log(
        client,
        "🟢 MATCH STARTED",
        match,
        "Match started in the group."
    )

    # Update message
    await query.message.edit_caption(
        caption=(
            "👑 <b>HOST CONFIRMED</b>\n\n"
            f"👤 Host: {mention_html(user)}\n"
            f"🏟 Venue: {group_title}\n\n"
            "➡️ Use /create_teams to continue"
        ),
        parse_mode=ParseMode.HTML
    )

@Client.on_callback_query(filters.regex("^mode_cancel$"))
async def cancel_game(client, query):
    await query.answer()
    await query.message.edit_text("`Game setup cancelled.`")
    
