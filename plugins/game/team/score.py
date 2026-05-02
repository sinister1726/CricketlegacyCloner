import time
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from plugins.game.team import ACTIVE_MATCHES
from plugins.game.team.scorecard import build_score_image, build_score_caption

SCORE_COOLDOWN = {}

@Client.on_message(filters.command("score") & filters.group)
async def score_cmd(client, message: Message):
    chat_id = message.chat.id
    current_time = time.time()

    if chat_id in SCORE_COOLDOWN and current_time - SCORE_COOLDOWN[chat_id] < 3:
        return

    match = ACTIVE_MATCHES.get(chat_id)
    if not match:
        return await message.reply_text(
            "😴 <b>It's quiet out there.</b>\nNo match running right now. Start now with /start",
            parse_mode=ParseMode.HTML
        )

    if match.get("mode") == "Solo":
        SCORE_COOLDOWN[chat_id] = current_time
        from plugins.game.solo import build_solo_score_text, PLAYZONE_BTN
        text = build_solo_score_text(match)
        return await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=PLAYZONE_BTN)

    if not match.get("client"):
        match["client"] = client

    if "innings" not in match:
        match["innings"] = 1

    bat_team = match.get("batting_team")
    if not bat_team:
        match["batting_team"] = "B" if match.get("innings") == 2 else "A"
        bat_team = match["batting_team"]

    if not match.get("bowling_team"):
        match["bowling_team"] = "B" if bat_team == "A" else "A"

    if not match.get("striker") or not match.get("non_striker"):
        return await message.reply_text("⏳ <b>Hold on!</b> Batters are being picked.", parse_mode=ParseMode.HTML)

    SCORE_COOLDOWN[chat_id] = current_time

    try:
        team_data = match.get("teams", {})

        for t_code in ["A", "B"]:
            if t_code not in team_data:
                team_data[t_code] = {"runs": 0, "wickets": 0, "balls": 0}
            if "balls" not in team_data[t_code]:
                team_data[t_code]["balls"] = 0

        bat_team_stats = team_data[bat_team]
        balls = bat_team_stats.get("balls", 0)

        overs_str = f"{balls // 6}.{balls % 6}"

        def get_score(t_key):
            t = team_data.get(t_key, {"runs": 0, "wickets": 0})
            return f"{t.get('runs', 0)}/{t.get('wickets', 0)}"

        match_data = {
            "score_a": get_score("A"),
            "score_b": get_score("B"),
            "overs": overs_str,
            "max_overs": match.get("overs", 0),
            "batting_team": bat_team,
            "innings": match.get("innings", 1),
            "target": match.get("target")
        }

        host_name = match.get("host_name", "Host")

        caption = build_score_caption(match, host_name)
        img = build_score_image(match_data)

        await message.reply_photo(
            photo=img,
            caption=caption,
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        print(f"Score System Error: {e}")
        try:
            host_name = match.get("host_name", "Host")
            caption = build_score_caption(match, host_name)
            await message.reply_text(f"📊 <b>Score Update (Text Mode):</b>\n\n{caption}", parse_mode=ParseMode.HTML)
        except Exception as inner_e:
            print(f"Critical Scorecard Failure: {inner_e}")
            await message.reply_text("❌ <b>Scorecard Sync Error. Please bowl one ball to re-initialize game state.</b>", parse_mode=ParseMode.HTML)

