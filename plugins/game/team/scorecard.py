import math
from database.connection import db
import os
import io
from PIL import Image, ImageDraw, ImageFont

SCORE_BG = "Assets/score.jpeg"
FONT_PATH = "Assets/fonts.ttf"
MAIN_SIZE = 110  
LABEL_SIZE = 40    
INFO_SIZE = 55    

def build_score_image(match_data):
    """
    ULTIMATE FIX: Standardizes coordinates, applies purple text color,
    recovers background gracefully if missing, and ensures buffer return.
    """
    try:
        if not os.path.exists(SCORE_BG):
            img = Image.new("RGBA", (1280, 720), color=(20, 24, 35, 255)) 
        else:
            img = Image.open(SCORE_BG).convert("RGBA")
    except Exception:
        img = Image.new("RGBA", (1280, 720), color=(20, 24, 35, 255))

    draw = ImageDraw.Draw(img)

    try:
        font_main = ImageFont.truetype(FONT_PATH, MAIN_SIZE)
        font_sub = ImageFont.truetype(FONT_PATH, LABEL_SIZE)
        font_info = ImageFont.truetype(FONT_PATH, INFO_SIZE)
    except Exception:
        font_main = font_sub = font_info = ImageFont.load_default()

    def draw_centered_text(text, font, x, y, fill="white", stroke_fill=None, stroke_width=0):
        bbox = draw.textbbox((0, 0), str(text), font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        draw.text((x - w/2, y - h/2), str(text), font=font, fill=fill, 
                  stroke_width=stroke_width, stroke_fill=stroke_fill)

    score_a = str(match_data.get("score_a", "0/0"))
    score_b = str(match_data.get("score_b", "0/0"))

    if match_data.get('innings', 1) == 1:
        if match_data.get('batting_team') == "A":
            score_b = "YTB"
        else:
            score_a = "YTB"

    center_x = 640

    left_slot_x = 450  
    left_slot_y = 370  

    right_slot_x = 980  
    right_slot_y = 370  

    y_overs = 580  
    y_target = 650

    text_purple = "#8A2BE2"

    draw_centered_text(score_a, font_main, left_slot_x, left_slot_y, fill=text_purple, stroke_width=2, stroke_fill="black")
    draw_centered_text(score_b, font_main, right_slot_x, right_slot_y, fill=text_purple, stroke_width=2, stroke_fill="black")

    overs_txt = f"OVERS: {match_data.get('overs', '0.0')} / {match_data.get('max_overs', '0')}"
    draw_centered_text(overs_txt, font_info, center_x, y_overs, fill="#00FFCC")

    if match_data.get('innings') == 2 and match_data.get('target'):
        target_txt = f"TARGET: {match_data['target']}"
        draw_centered_text(target_txt, font_sub, center_x, y_target, fill="#FF4444")

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=95)
    buf.seek(0)

    img.close()

    return buf
    
def build_score_caption(match, host_name):
    """
    UPGRADED SCORE CAPTION
    - No design changes
    - Adds intelligence & broadcast-level insights
    - Safe against crashes
    """
    
    bat = match.get("batting_team", "A")
    bowl = match.get("bowling_team", "B")

    teams = match.get("teams", {})
    bat_team = teams.get(bat, {"runs": 0, "wickets": 0, "balls": 0})
    bowl_team = teams.get(bowl, {"runs": 0, "wickets": 0, "balls": 0})

    actual_balls = bat_team.get("balls", 0)
    runs = bat_team.get("runs", 0)
    wickets = bat_team.get("wickets", 0)

    overs_formatted = f"{actual_balls // 6}.{actual_balls % 6}"
    crr = round((runs * 6 / actual_balls), 2) if actual_balls else 0.0

    players = match.get("players", {})
    user_cache = match.get("user_cache", {})

    text = (
        f"╾ ⏳ <b>Total Overs:</b> {match.get('overs', 0)}\n"
        f"╾ 📯 <b>Host:</b> {host_name}\n"
        "────┈┄┄╌╌╌╌┄┄┈────\n"
        f"<b>🏏 Batting: Team {bat}</b>\n\n"
    )

    s_id = match.get("striker")
    ns_id = match.get("non_striker")

    for uid in [s_id, ns_id]:
        if not uid:
            continue

        p = players.get(uid, {})
        name = user_cache.get(uid, "Player")

        p_runs = p.get("runs", 0)
        p_balls = p.get("balls_faced", 0)
        sr = round((p_runs / p_balls) * 100, 1) if p_balls else 0.0

        star = " 🏏" if uid == s_id else ""
        form = ""

        if p_balls >= 10:
            if sr >= 150:
                form = " 🔥"
            elif sr <= 80:
                form = " ⚠️"

        text += f"✧ {name} = {p_runs}({p_balls}){star}{form}\n╰⊚ (SR: {sr})\n"

    if match.get("partnership") or match.get("partnership_balls"):
        text += f"🤝 <b>Partnership:</b> {match.get('partnership',0)}({match.get('partnership_balls',0)})\n"

    text += "────┈┄┄╌╌╌╌┄┄┈────\n"

    bowler_uid = match.get("current_bowler")
    if bowler_uid:
        b_name = user_cache.get(bowler_uid, "Bowler")
        b = players.get(bowler_uid, {})

        history = match.get("current_over_balls", [])
        history_txt = " • ".join(map(str, history)) if history else "Starting over..."

        b_balls = b.get("balls_bowled", 0)
        b_runs = b.get("runs_conceded", 0)
        econ = round((b_runs * 6 / b_balls), 2) if b_balls else 0.0

        text += (
            f"<b>⚾ Bowling: Team {bowl}</b>\n\n"
            f"👤 {b_name}\n"
            f"╰⊚ Over: [{history_txt}]\n"
            f"╰⊚ Econ: <b>{econ}</b>\n"
            "────┈┄┄╌╌╌╌┄┄┈────\n"
        )

    text += (
        f"👥 <b>Total Score:</b> {runs}/{wickets} ({overs_formatted} ov)\n"
        f"╰⊚ <b>CRR:</b> {crr}\n"
    )
    
    dots = bat_team.get("over_history", []).count(0)
    if actual_balls:
        dot_pct = int((dots / actual_balls) * 100)
        text += f"🧱 <b>Dot Balls:</b> {dots} ({dot_pct}%)\n"

    recent = bat_team.get("over_history", [])[-12:]
    recent_runs = sum(x for x in recent if isinstance(x, int))
    recent_wkts = recent.count("W")

    if recent_wkts >= 2:
        momentum = "🔴 Bowling on top"
    elif recent_runs >= 18:
        momentum = "🟢 Batting accelerating"
    else:
        momentum = "⚖️ Even contest"

    text += f"📊 <b>Momentum:</b> {momentum}\n"

    if match.get("innings") == 2:
        text += "⊱⋅ ──────────── ⋅⊰\n"

        prev_runs = bowl_team.get("runs", 0)
        prev_wkts = bowl_team.get("wickets", 0)
        prev_balls = bowl_team.get("balls", match.get("overs", 1) * 6)
        prev_overs = f"{prev_balls // 6}.{prev_balls % 6}"

        target = match.get("target", 0)
        balls_left = max(0, match.get("overs", 0) * 6 - actual_balls)
        runs_needed = max(0, target - runs)
        rrr = round((runs_needed * 6 / balls_left), 2) if balls_left else 0.0

        text += (
            f"🏁 <b>Team {bowl}:</b> {prev_runs}/{prev_wkts} ({prev_overs} ov)\n"
            f"🎯 <b>Target:</b> {target}\n"
            f"╰⊚ Need <b>{runs_needed}</b> runs in <b>{balls_left}</b> balls\n"
            f"📈 <b>RRR:</b> {rrr}\n"
        )

        text += "<i>⚠️ Required rate rising</i>\n" if rrr > crr else "<i>✅ Chase under control</i>\n"

    footer = (
        "ℹ️ Early wickets can flip the game."
        if match.get("innings") == 1
        else "🏁 Every ball matters now."
    )

    text += f"\n<i>{footer}</i>"

    return text

def build_final_summary_image(match_data):
    """
    Renders the final match summary with top performers using custom name fonts.
    Layout: Team Scores at top, Boxes for Best Batsman/Bowler, and Winner at bottom.
    """
    if not os.path.exists(SCORE_BG):
        img = Image.new("RGBA", (1280, 1000), color=(20, 24, 35, 255))
    else:
        img = Image.open(SCORE_BG).convert("RGBA").resize((1280, 1000))

    draw = ImageDraw.Draw(img)

    NAME_FONTS = ["Assets/namefont.ttf"]

    try:
        font_lg = ImageFont.truetype(FONT_PATH, 90) 
        font_md = ImageFont.truetype(FONT_PATH, 45)  
        font_sm = ImageFont.truetype(FONT_PATH, 32) 

        font_name = None
        for path in NAME_FONTS:
            if os.path.exists(path):
                font_name = ImageFont.truetype(path, 40)
                break
        if not font_name:
            font_name = ImageFont.truetype(FONT_PATH, 40)

    except Exception as e:
        print(f"Font Load Error: {e}")
        font_lg = font_md = font_sm = font_name = ImageFont.load_default()

    def draw_box(x, y, w, h, title, player_name, stats_list, color):
        """Draws box with specialized font for the player name."""
        draw.rounded_rectangle([x, y, x+w, y+h], radius=20, fill=(30, 34, 45, 220), outline=color, width=4)

        draw.text((x + 25, y + 15), title.upper(), font=font_md, fill=color)

        draw.text((x + 25, y + 75), player_name, font=font_name, fill="white")

        for i, stat in enumerate(stats_list):
            draw.text((x + 25, y + 130 + (i * 45)), stat, font=font_sm, fill="#CCCCCC")

    y_scores = 120
    y_boxes_top = 280
    y_boxes_bot = 580
    y_winner = 880

    draw.text((120, y_scores), f"TEAM A: {match_data['score_a']}", font=font_lg, fill="white")
    draw.text((720, y_scores), f"TEAM B: {match_data['score_b']}", font=font_lg, fill="white")

    draw_box(100, y_boxes_top, 520, 270, "Best Batsman (A)", 
             match_data['bat_a_name'], 
             [f"Runs: {match_data['bat_a_r']} ({match_data['bat_a_b']}b)", f"4s: {match_data['bat_a_4']} | 6s: {match_data['bat_a_6']}"], "#FF3131")

    draw_box(100, y_boxes_bot, 520, 270, "Best Bowler (A)", 
             match_data['bowl_a_name'], 
             [f"Wickets: {match_data['bowl_a_w']}", f"Runs Conceded: {match_data['bowl_a_r_c']}"], "#FF3131")

    draw_box(660, y_boxes_bot, 520, 270, "Best Batsman (B)", 
             match_data['bat_b_name'], 
             [f"Runs: {match_data['bat_b_r']} ({match_data['bat_b_b']}b)", f"4s: {match_data['bat_b_4']} | 6s: {match_data['bat_b_6']}"], "#007FFF")

    draw_box(660, y_boxes_bot, 520, 270, "Best Bowler (B)", 
             match_data['bowl_b_name'], 
             [f"Wickets: {match_data['bowl_b_w']}", f"Runs Conceded: {match_data['bowl_b_r_c']}"], "#007FFF")

    winner_text = f"🏆 {match_data['winner_name'].upper()} WON THE MATCH!"
    bbox = draw.textbbox((0, 0), winner_text, font=font_lg)
    w_text = bbox[2] - bbox[0]
    draw.text((640 - w_text/2, y_winner), winner_text, font=font_lg, fill="#FFD700", stroke_width=2, stroke_fill="black")

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return buf

async def save_match_stats(match, winner_team):
    """
    SAVES FINAL RESULTS + CAREER STATS (MOM, Highest Score, Partnership, boundaries)
    Uses an atomic transaction to ensure data integrity.
    """
    from database.connection import db

    game_id = match.get("game_id")
    players = match.get("players", {})

    if not game_id or "teams" not in match or not players:
        print(f"⚠️ Stats skip: Match {game_id} has incomplete memory data.")
        return
        
    motm_id = None
    max_points = -1
    for uid, p in players.items():
        points = p.get("runs", 0) + (p.get("wickets", 0) * 25)
        if p.get("team") == winner_team:
            points += 10
        if points > max_points:
            max_points = points
            motm_id = uid

    team_a = match["teams"].get("A", {"runs": 0, "wickets": 0})
    team_b = match["teams"].get("B", {"runs": 0, "wickets": 0})

    await db.db["games"].update_one(
        {"game_id": game_id},
        {"$set": {
            "status": "finished",
            "winner": winner_team,
            "team_a_runs": team_a.get("runs", 0),
            "team_b_runs": team_b.get("runs", 0),
            "team_a_wickets": team_a.get("wickets", 0),
            "team_b_wickets": team_b.get("wickets", 0),
        }}
    )

    from datetime import datetime
    for uid, p in players.items():
        is_winner = 1 if p.get("team") == winner_team else 0
        is_loser = 1 if (winner_team not in ["Tie", "No Result", None] and p.get("team") != winner_team) else 0
        is_mom = 1 if uid == motm_id else 0

        runs = p.get("runs", 0)
        wickets = p.get("wickets", 0)
        fours = p.get("fours_count", 0)
        sixes = p.get("sixes_count", 0)
        b_faced = p.get("balls_faced", 0)
        b_bowled = p.get("balls_bowled", 0)
        r_conceded = p.get("runs_conceded", 0)

        is_50 = 1 if 50 <= runs < 100 else 0
        is_100 = 1 if runs >= 100 else 0
        is_duck = 1 if runs == 0 and p.get("is_out") else 0

        form_char = "W" if p.get("team") == winner_team else "L"

        existing = await db.db["user_stats"].find_one({"user_id": uid})
        if existing:
            old_form = existing.get("recent_form", "") or ""
            new_form = (form_char + old_form)[:5]
            old_hs = existing.get("highest_score", 0) or 0
            await db.db["user_stats"].update_one(
                {"user_id": uid},
                {"$inc": {
                    "matches": 1, "wins": is_winner, "losses": is_loser,
                    "runs": runs, "wickets": wickets, "balls_faced": b_faced,
                    "balls_bowled": b_bowled, "runs_conceded": r_conceded,
                    "fours": fours, "sixes": sixes, "moms": is_mom,
                    "centuries": is_100, "fifties": is_50, "ducks": is_duck,
                }, "$max": {
                    "highest_score": runs,
                }, "$set": {
                    "recent_form": new_form,
                    "last_played_at": datetime.utcnow(),
                }}
            )
        else:
            await db.db["user_stats"].insert_one({
                "user_id": uid,
                "matches": 1, "wins": is_winner, "losses": is_loser,
                "runs": runs, "wickets": wickets, "balls_faced": b_faced,
                "balls_bowled": b_bowled, "runs_conceded": r_conceded,
                "fours": fours, "sixes": sixes, "moms": is_mom,
                "centuries": is_100, "fifties": is_50, "ducks": is_duck,
                "highest_score": runs, "recent_form": form_char,
                "last_played_at": datetime.utcnow(),
            })

    partnership_runs = match.get("best_partnership_this_match", match.get("partnership", 0))
    for pid in list(players.keys()):
        if pid:
            await db.db["user_stats"].update_one(
                {"user_id": pid},
                {"$max": {"best_partnership": partnership_runs}}
            )

    try:
        from database.venue_stats import update_venue_stats
        chat_id    = match.get("chat_id")
        chat_title = (
            match.get("chat_title")
            or match.get("group_name")
            or match.get("title")
            or match.get("group_title")
        )
        if chat_id and not chat_title:
            try:
                _chat = await match["client"].get_chat(chat_id)
                chat_title = _chat.title or f"Group {chat_id}"
            except Exception:
                chat_title = f"Group {chat_id}"
        if chat_id:
            for uid, p in players.items():
                await update_venue_stats(
                    uid,
                    chat_id,
                    chat_title,
                    p.get("runs", 0),
                    p.get("wickets", 0),
                )
    except Exception as _ve:
        print(f"Venue stats save error: {_ve}")

    try:
        from database.group_records import update_group_records
        await update_group_records(match, players, winner_team)
    except Exception as _gr:
        print(f"Group records update error: {_gr}")

    print(f"✅ Match {game_id} full stats and milestones saved.")
