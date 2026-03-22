from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.game.team import ACTIVE_MATCHES


PLAYZONE_BTN = InlineKeyboardMarkup([[
    InlineKeyboardButton("ʟᴇɢᴀᴄʏ ᴘʟᴀʏᴢᴏɴᴇ 🏏", url="https://t.me/CLG_fun_zone")
]])


def get_next_solo_bowler(match):
    players = match["players"]
    current_batter = match["current_batter"]
    n = len(players)
    start_pos = match.get("bowler_rotation_pos", 1)
    for offset in range(n):
        pos = (start_pos + offset) % n
        candidate = players[pos]
        if candidate != current_batter:
            match["bowler_rotation_pos"] = (pos + 1) % n
            return candidate
    return None


def advance_solo_bowler(match):
    next_b = get_next_solo_bowler(match)
    match["current_bowler"] = next_b
    match["balls_in_spell"] = 0
    return next_b


def _calc_sr(runs, balls):
    if balls == 0:
        return "0.0"
    return f"{(runs / balls * 100):.1f}"


def build_solo_score_text(match):
    players = match.get("players", [])
    user_cache = match.get("user_cache", {})
    stats = match.get("player_stats", {})

    lines = ["≪━─━─━◈ <b>Sᴏʟᴏ Sᴄᴏʀᴇ</b> ◈━─━─━≫\n"]

    for uid in players:
        p = stats.get(uid, {})
        name = user_cache.get(uid, "Player")
        runs = p.get("runs", 0)
        balls = p.get("balls_faced", 0)
        fours = p.get("fours_count", 0)
        sixes = p.get("sixes_count", 0)
        b_bowled = p.get("balls_bowled", 0)
        wkts = p.get("wickets", 0)
        r_conceded = p.get("runs_conceded", 0)
        sr = _calc_sr(runs, balls)

        lines.append(
            f"❖ <b>{name}</b> — {runs} ({balls})\n"
            f"➥ 4️⃣: {fours} | 6️⃣: {sixes} ⟶ SR : {sr}\n"
            f"➥ Bowling: {b_bowled} balls | {wkts} wkts | {r_conceded} runs"
        )

    total_runs = match.get("total_runs", 0)
    total_balls = match.get("total_balls", 0)
    overs = f"{total_balls // 6}.{total_balls % 6}"
    lines.append(f"\n╰⊚ <b>Total:</b> {total_runs} in {overs} overs")

    return "\n\n".join(lines)
