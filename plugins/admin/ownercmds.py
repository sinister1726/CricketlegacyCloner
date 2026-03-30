import html
import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from database.connection import db

OWNER_FILTER = filters.user(list(Config.OWNER_IDS))

# Pending broadcast sessions: {user_id: {"from_chat": ..., "msg_id": ...}}
_pending_broadcasts: dict = {}

EDITABLE_STATS = {
    "matches", "wins", "losses", "runs", "balls_faced", "highest_score",
    "fours", "sixes", "centuries", "fifties", "ducks", "wickets",
    "balls_bowled", "runs_conceded", "hat_tricks", "moms",
}


async def _resolve_user(client, identifier):
    identifier = identifier.strip()
    if identifier.lstrip("-").isdigit():
        try:
            return await client.get_users(int(identifier))
        except Exception:
            return None
    try:
        return await client.get_users(identifier)
    except Exception:
        return None


@Client.on_message(filters.command("resetstats") & OWNER_FILTER)
async def reset_stats_cmd(client, message):
    args = message.command

    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(args) >= 2:
        wait = await message.reply_text("🔍 Looking up user…")
        target = await _resolve_user(client, args[1])
        await wait.delete()
    else:
        return await message.reply_text(
            "⚠️ <b>Usage:</b>\n"
            "• Reply to a message: <code>/resetstats</code>\n"
            "• By ID/username: <code>/resetstats [user_id or @username]</code>",
            parse_mode=ParseMode.HTML,
        )

    if not target:
        return await message.reply_text("❌ User not found.")

    confirm_btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes, Reset", callback_data=f"ownerreset:{target.id}"),
        InlineKeyboardButton("❌ Cancel", callback_data="ownerreset:cancel"),
    ]])
    await message.reply_text(
        f"⚠️ <b>Reset all stats for</b> <a href='tg://user?id={target.id}'>{html.escape(target.first_name)}</a> "
        f"(<code>{target.id}</code>)?\n\n"
        "This will <b>wipe</b> matches, runs, wickets, wins, losses and all records.",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_btn,
    )


@Client.on_callback_query(filters.regex(r"^ownerreset:(.+)$") & OWNER_FILTER)
async def reset_stats_confirm(client, query):
    payload = query.data.split(":", 1)[1]
    if payload == "cancel":
        await query.message.delete()
        return await query.answer("Cancelled.")

    user_id = int(payload)
    await query.answer("Resetting…")
    try:
        await db.db["user_stats"].update_one(
            {"user_id": user_id},
            {"$set": {
                "matches": 0, "wins": 0, "losses": 0, "runs": 0,
                "balls_faced": 0, "highest_score": 0, "fours": 0,
                "sixes": 0, "centuries": 0, "fifties": 0, "ducks": 0,
                "wickets": 0, "balls_bowled": 0, "runs_conceded": 0,
                "hat_tricks": 0, "moms": 0, "best_partnership": 0,
                "penalties_received": 0, "recent_form": "", "last_played_at": None,
            }}
        )
        await db.db["duel_stats"].update_one(
            {"user_id": user_id},
            {"$set": {
                "wins": 0, "losses": 0, "matches": 0,
                "runs": 0, "wickets": 0, "highest_score": 0, "ducks": 0,
            }}
        )
        await query.message.edit_text(
            f"✅ <b>Stats reset</b> for user <code>{user_id}</code>.\n"
            f"Duel stats also cleared.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await query.message.edit_text(f"❌ Error: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("editstat") & OWNER_FILTER)
async def edit_stat_cmd(client, message):
    args = message.command

    if message.reply_to_message and len(args) >= 3:
        target = message.reply_to_message.from_user
        field = args[1].lower()
        raw_val = args[2]
    elif len(args) >= 4:
        wait = await message.reply_text("🔍 Looking up user…")
        target = await _resolve_user(client, args[1])
        await wait.delete()
        field = args[2].lower()
        raw_val = args[3]
    else:
        fields_list = " | ".join(sorted(EDITABLE_STATS))
        return await message.reply_text(
            "⚠️ <b>Usage:</b>\n"
            "• Reply + <code>/editstat [field] [value]</code>\n"
            "• <code>/editstat [user_id] [field] [value]</code>\n\n"
            f"<b>Editable fields:</b>\n<code>{fields_list}</code>",
            parse_mode=ParseMode.HTML,
        )

    if not target:
        return await message.reply_text("❌ User not found.")

    if field not in EDITABLE_STATS:
        return await message.reply_text(
            f"❌ Unknown field <code>{html.escape(field)}</code>.\n"
            f"Allowed: <code>{' | '.join(sorted(EDITABLE_STATS))}</code>",
            parse_mode=ParseMode.HTML,
        )

    try:
        value = int(raw_val)
        if value < 0:
            return await message.reply_text("❌ Value must be ≥ 0.")
    except ValueError:
        return await message.reply_text("❌ Value must be a whole number.")

    try:
        result = await db.db["user_stats"].update_one(
            {"user_id": target.id},
            {"$set": {field: value}}
        )
        if result.matched_count == 0:
            return await message.reply_text(
                f"⚠️ No stats row found for <code>{target.id}</code>. "
                "They need to play at least one match first.",
                parse_mode=ParseMode.HTML,
            )
        await message.reply_text(
            f"✅ <b>{html.escape(target.first_name)}</b>'s "
            f"<code>{field}</code> set to <b>{value}</b>.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await message.reply_text(f"❌ Error: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("botstats") & OWNER_FILTER)
async def bot_stats_cmd(client, message):
    wait = await message.reply_text("📊 Fetching stats…")
    try:
        total_users = await db.db["user_stats"].count_documents({})
        total_matches = await db.db["games"].count_documents({})
        active_matches = await db.db["games"].count_documents({"status": "active"})
        duel_count = await db.db["duel_stats"].count_documents({})

        pipeline_runs = [{"$group": {"_id": None, "total": {"$sum": "$runs"}}}]
        pipeline_wkts = [{"$group": {"_id": None, "total": {"$sum": "$wickets"}}}]

        runs_res = await db.db["user_stats"].aggregate(pipeline_runs).to_list(1)
        wkts_res = await db.db["user_stats"].aggregate(pipeline_wkts).to_list(1)
        total_runs = runs_res[0]["total"] if runs_res else 0
        total_wickets = wkts_res[0]["total"] if wkts_res else 0

        top_batter = await db.db["user_stats"].find_one(
            {}, {"first_name": 1, "runs": 1}, sort=[("runs", -1)]
        )
        top_bowler = await db.db["user_stats"].find_one(
            {}, {"first_name": 1, "wickets": 1}, sort=[("wickets", -1)]
        )

        tb_name = html.escape(top_batter.get("first_name") or "—") if top_batter else "—"
        tb_runs = top_batter.get("runs", 0) if top_batter else 0
        twk_name = html.escape(top_bowler.get("first_name") or "—") if top_bowler else "—"
        twk_wkts = top_bowler.get("wickets", 0) if top_bowler else 0

        text = (
            "📊 <b>BOT STATISTICS</b>\n"
            "────┈┄┄╌╌╌╌┄┄┈────\n\n"
            f"👥 <b>Total Players:</b> {total_users:,}\n"
            f"🏏 <b>Total Matches:</b> {total_matches:,}\n"
            f"🔴 <b>Live Matches:</b> {active_matches}\n"
            f"⚔️ <b>Duel Players:</b> {duel_count:,}\n\n"
            f"🏃 <b>Total Runs Scored:</b> {total_runs:,}\n"
            f"🎯 <b>Total Wickets:</b> {total_wickets:,}\n\n"
            f"👑 <b>Top Batter:</b> {tb_name} ({tb_runs:,} runs)\n"
            f"🏆 <b>Top Bowler:</b> {twk_name} ({twk_wkts} wkts)"
        )
        await wait.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await wait.edit_text(f"❌ Error: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("givemom") & OWNER_FILTER)
async def give_mom_cmd(client, message):
    args = message.command
    target = None

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(args) >= 2:
        wait = await message.reply_text("🔍 Looking up…")
        target = await _resolve_user(client, args[1])
        await wait.delete()
    else:
        return await message.reply_text("⚠️ Reply to a user or use <code>/givemom [user_id]</code>", parse_mode=ParseMode.HTML)

    if not target:
        return await message.reply_text("❌ User not found.")

    try:
        await db.db["user_stats"].update_one(
            {"user_id": target.id},
            {"$inc": {"moms": 1}},
            upsert=True,
        )
        await message.reply_text(
            f"🏅 <b>Man of the Match</b> awarded to "
            f"<a href='tg://user?id={target.id}'>{html.escape(target.first_name)}</a>!",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await message.reply_text(f"❌ Error: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
