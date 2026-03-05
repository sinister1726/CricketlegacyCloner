import asyncio
from pyrogram.enums import ParseMode
from plugins.game.team import ACTIVE_MATCHES
import random
from database.connection import db 
from plugins.game.team.summaries import (
    build_over_summary,
    build_innings_summary,
    build_match_summary,
)
from plugins.utilities.graph import get_graph_buffer
from plugins.utilities.achieve import evaluate_and_unlock_achievements

NVIDIA_API_KEY = "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"

BALLS_PER_OVER = 6
from html import escape

def safe_name(name: str) -> str:
    return escape(name or "Player")

def get_mention(match, user_id):
    name = match.get("user_cache", {}).get(user_id, "Player")
    return f'<a href="tg://user?id={user_id}">{name}</a>'

import random

def _mention(user_id, match):
    name = match.get("user_cache", {}).get(user_id, "Player")
    return f"<a href='tg://user?id={user_id}'>{name}</a>"

BATTER_LINES = {
    50: [
        "{p} raises the bat 🏏 Half-century loaded.",
        "Classy stuff! {p} cruises to 50.",
        "Fifty up! {p} is cooking now 🔥",
        "{p} completes a well-earned 50. Respect."
    ],
    100: [
        "CENTURY! 💯 {p} has rewritten the script.",
        "{p} goes full beast mode 💥 Hundred on the board.",
        "Standing ovation 👏 {p} brings up a ton.",
        "What a knock! {p} hits 100 in style."
    ],
    150: [
        "150! This is domination by {p}.",
        "{p} refuses to stop. 150 and counting 👑",
        "Absolute massacre. {p} reaches 150."
    ],
    250: [
        "HISTORY ALERT 🚨 {p} smashes 250!",
        "Unreal innings… {p} hits 250 😵‍💫",
        "This is illegal batting. 250 for {p}."
    ]
}

BOWLER_LINES = {
    3: [
        "{p} strikes thrice 🎯 3-wicket haul!",
        "Bowling clinic! {p} picks up 3.",
        "{p} is on fire 🔥 Three wickets down!"
    ],
    5: [
        "FIVE-FOR! 🖐️ {p} demolishes the batting.",
        "{p} claims a 5-wicket haul. Carnage.",
        "Bowling royalty 👑 5 wickets for {p}."
    ],
    "HAT_TRICK": [
        "HAT-TRICK 🎩🎩🎩 {p} has lost his mind!",
        "Three in three! {p} goes nuclear 💣",
        "Hat-trick scenes 😱 Courtesy: {p}"
    ]
}

PARTNERSHIP_LINES = {
    50: [
        "{p1} & {p2} build a solid 50-run stand 🤝",
        "Good vibes only 😌 50 partnership!"
    ],
    100: [
        "CENTURY STAND 💯 {p1} & {p2} are unstoppable!",
        "What a partnership! 100 runs together 🔥"
    ]
}

async def announce_achievement_group(client, chat_id, achievement, match):
    """
    achievement = dict returned by evaluate_and_unlock_achievements
    Example:
    {
        "type": "BAT_50",
        "user_id": 123,
        "value": 50
    }
    """

    t = achievement["type"]

    if t.startswith("BAT_"):
        runs = achievement["value"]
        user_id = achievement["user_id"]
        p = _mention(user_id, match)

        lines = BATTER_LINES.get(runs)
        if not lines:
            return

        text = random.choice(lines).format(p=p)

    elif t.startswith("BOWL_"):
        wickets = achievement["value"]
        user_id = achievement["user_id"]
        p = _mention(user_id, match)

        if wickets == 3:
            text = random.choice(BOWLER_LINES[3]).format(p=p)
        elif wickets == 5:
            text = random.choice(BOWLER_LINES[5]).format(p=p)
        else:
            return

    elif t == "HAT_TRICK":
        user_id = achievement["user_id"]
        p = _mention(user_id, match)
        text = random.choice(BOWLER_LINES["HAT_TRICK"]).format(p=p)

    elif t.startswith("PARTNERSHIP_"):
        value = achievement["value"]
        p1 = _mention(achievement["p1"], match)
        p2 = _mention(achievement["p2"], match)

        lines = PARTNERSHIP_LINES.get(value)
        if not lines:
            return

        text = random.choice(lines).format(p1=p1, p2=p2)

    else:
        return

    await client.send_message(
        chat_id,
        f"🏆 <b>Achievement Unlocked!</b>\n<i>{text}</i>",
        parse_mode=ParseMode.HTML
    )

async def announce_achievement_dm(client, user_id, achievement):
    try:
        await client.send_message(
            user_id,
            f"🏆 Achievement unlocked!\n\n{achievement.get('title','Nice one!')} 🎉"
        )
    except:
        pass

def should_announce_in_group(ach):
    cond = normalize_condition(ach["condition"])

    if ach["rarity"] in ("rare", "epic", "legendary"):
        return True

    if cond.get("scope") in ("match", "innings"):
        return True

    return False
    
def normalize_condition(cond):
    if cond is None:
        return {}
    if isinstance(cond, dict):
        return cond
    if isinstance(cond, str):
        try:
            return json.loads(cond)
        except Exception:
            return {}
    return {}

async def update_game_in_db(match):
    try:
        game_id = match.get("game_id")
        if not game_id:
            return print("⚠️ Skipping DB sync: match['game_id'] is missing.")

        teams = match.get("teams", {})
        team_a = teams.get("A", {"runs": 0, "wickets": 0, "balls": 0})
        team_b = teams.get("B", {"runs": 0, "wickets": 0, "balls": 0})

        async with db.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE games 
                SET team_a_runs = $1, 
                    team_b_runs = $2, 
                    team_a_wickets = $3, 
                    team_b_wickets = $4, 
                    phase = $5, 
                    batting_team = $6, 
                    bowling_team = $7,
                    target = $8,
                    innings = $9,
                    team_a_balls = $10,
                    team_b_balls = $11
                WHERE game_id = $12
                """,
                team_a.get("runs", 0), 
                team_b.get("runs", 0),
                team_a.get("wickets", 0), 
                team_b.get("wickets", 0),
                match.get("phase", "LIVE"), 
                match.get("batting_team", "A"), 
                match.get("bowling_team", "B"),
                match.get("target"),       
                match.get("innings", 1),  
                team_a.get("balls", 0), 
                team_b.get("balls", 0), 
                game_id
            )

    except Exception as e:
        print(f"❌ DB Sync Error in game {match.get('game_id')}: {e}")

async def advance_ball(match, result):
    match.setdefault("announced_achievements", {
        "batting": {},  
        "bowling": {},  
        "partnerships": set() 
    })

    print(f"➡️ advance_ball ENTER | result = {result} | balls_so_far = {len(match.get('current_over_balls', []))}")

    if len(match.get("current_over_balls", [])) >= 6:
        print("⚠️ Over already finished. Triggering end_over.")
        from plugins.game.team.over_engine import end_over
        return await end_over(match)

    client = match.get("client")
    has_client = client is not None  

    if not has_client:
        print("⚠️ client missing — attempting recovery")
        from plugins.game.team.init import ACTIVE_MATCHES
        if match.get("chat_id") in ACTIVE_MATCHES:
            match["client"] = client

    chat_id = match.get("chat_id")
    if not chat_id:
        return

    actual_striker = match.get("striker")
    bowler_id = match.get("current_bowler")

    if not actual_striker or not bowler_id:
        print("⚠️ striker/bowler missing — aborting ball")
        return

    bat_team_key = match.get("batting_team", "A")
    bat_team = match.get("teams", {}).get(bat_team_key)
    
    if not bat_team:
        return

    bat_team.setdefault("balls", 0)
    
    for key in ["total_balls", "ball_in_over", "partnership", "partnership_balls"]:
        match.setdefault(key, 0)
    match.setdefault("current_over_balls", [])

    try:
        if isinstance(result, int):
            runs = result
            bat_team["runs"] += runs
            bat_team["balls"] += 1
            bat_team.setdefault("over_history", []).append(runs) 

            match["partnership"] += runs
            match["partnership_balls"] += 1
            
            if has_client:
                s = match.get("striker")
                ns = match.get("non_striker")
                if s and ns:
                    for value in (50, 100):
                        key = tuple(sorted((s, ns)) + [value])
                        if match["partnership"] >= value and key not in match["announced_achievements"]["partnerships"]:
                            match["announced_achievements"]["partnerships"].add(key)
                            msg = {50: "Nice stand 🤝 {p1} & {p2} cross 50", 100: "CENTURY STAND 💯 {p1} & {p2} are unstoppable!"}
                            await client.send_message(chat_id, f"🏆 <b>Achievement!</b>\n<i>{msg[value].format(p1=_mention(s, match), p2=_mention(ns, match))}</i>", parse_mode=ParseMode.HTML)

            if actual_striker in match["players"]:
                p = match["players"][actual_striker]
                p["runs"] += runs
                p["balls_faced"] += 1
                
                if has_client:
                    announced = match["announced_achievements"]["batting"].setdefault(actual_striker, set())
                    for milestone in (50, 100, 150, 250):
                        if p["runs"] >= milestone and milestone not in announced:
                            announced.add(milestone)
                            lines = {50: "{p} brings up a classy 50 🏏", 100: "CENTURY 💯 {p} is on fire!", 150: "150 up 😬 Domination by {p}", 250: "🚨 HISTORY 🚨 {p} smashes 250!"}
                            await client.send_message(chat_id, f"🏆 <b>Achievement!</b>\n<i>{lines[milestone].format(p=_mention(actual_striker, match))}</i>", parse_mode=ParseMode.HTML)

                if runs == 4: p["fours_count"] = p.get("fours_count", 0) + 1
                elif runs == 6: p["sixes_count"] = p.get("sixes_count", 0) + 1
                    
            if bowler_id in match["players"]:
                b = match["players"][bowler_id]
                b["runs_conceded"] += runs
                b["balls_bowled"] += 1
                b.setdefault("bowling_balls", []).append(result)

            match["current_over_balls"].append(result)
            match["total_balls"] += 1
            match["_rotate_next_ball"] = (runs % 2 != 0)
            match["_last_ball_runs"] = runs
            
            if match.get("innings") == 2 and match.get("target"):
                bowling_team = match.get("bowling_team")
                
                bat_runs = match["teams"][bat_team_key]["runs"]
                target_runs = match["teams"][bowling_team]["runs"]
                
                if bat_runs > target_runs:
                    if has_client:
                        await client.send_message(
                            chat_id,
                            f"🏆 **𝗧𝗔𝗥𝗚𝗘𝗧 𝗖𝗛𝗔𝗦𝗘𝗗!**\n"
                            f"──┈┄┄╌╌╌╌┄┄┈──\n"
                            f"Team {bat_team_key} has successfully chased the target!\n"
                            f"They win the match! 🎉",
                            parse_mode=ParseMode.HTML
                        )
                    
                    match.update({"phase": "finished", "striker": None, "non_striker": None})
                    from plugins.game.team.over_engine import update_game_in_db, end_match
                    await update_game_in_db(match)
                    await end_match(match)
                    return 
                
        elif result == "W":
            match.pop("_rotate_next_ball", None)
            bat_team["wickets"] += 1
            bat_team["balls"] += 1
            bat_team.setdefault("over_history", []).append(0)
            match["partnership"] = match["partnership_balls"] = 0
            match["_last_ball_runs"] = None

            if actual_striker in match["players"]:
                p = match["players"][actual_striker]
                p["balls_faced"] += 1
                p["is_out"] = True

            try:
                from database.connection import db
                async with db.pool.acquire() as conn:
                    await conn.execute("UPDATE game_players SET role = NULL, is_out = TRUE WHERE game_id = $1 AND user_id = $2", match.get("game_id"), actual_striker)
            except Exception as e:
                print("❌ DB role clear failed:", e)

            if bowler_id in match["players"]:
                b = match["players"][bowler_id]
                b["balls_bowled"] += 1
                b["wickets"] = b.get("wickets", 0) + 1
                
                if has_client:
                    announced = match["announced_achievements"]["bowling"].setdefault(bowler_id, set())
                    if b["wickets"] in (3, 5) and b["wickets"] not in announced:
                        announced.add(b["wickets"])
                        msg = {3: "{p} picks up a 3-fer 🎯", 5: "FIVE-FOR 🖐️ {p} destroys the batting!"}
                        await client.send_message(chat_id, f"🏆 <b>Achievement!</b>\n<i>{msg[b['wickets']].format(p=_mention(bowler_id, match))}</i>", parse_mode=ParseMode.HTML)
                        
                    balls = b.get("bowling_balls", [])
                    if len(balls) >= 3 and balls[-3:] == ["W", "W", "W"] and "HAT" not in announced:
                        announced.add("HAT")
                        await client.send_message(chat_id, f"🎩 <b>HAT-TRICK!</b>\n<i>{_mention(bowler_id, match)} takes three in three 😱</i>", parse_mode=ParseMode.HTML)

            match["current_over_balls"].append("W")
            match["total_balls"] += 1

            is_last_ball_wicket = len(match["current_over_balls"]) >= 6
            
            from plugins.game.team.over_engine import update_game_in_db
            await update_game_in_db(match)

            total_players = len(bat_team.get("players", []))
            is_all_out = bat_team["wickets"] >= total_players - 1

            if is_all_out:
                match.update({"phase": "finished", "striker": None, "non_striker": None})
                if has_client:
                    await client.send_message(chat_id, f"☝️ <b>WICKET!</b>\n🚫 <b>ALL OUT!</b>\n\n<i>Complete collapse. Innings closed.</i>", parse_mode=ParseMode.HTML)
                
                from plugins.game.team.over_engine import end_match, end_innings
                if match.get("innings") == 2:
                    await end_match(match)
                else:
                    await end_innings(match)
                return

            if is_last_ball_wicket:
                match.update({"striker": match.get("non_striker"), "non_striker": None})
                if has_client:
                    await client.send_message(chat_id, "☝️ <b>WICKET!</b>\n<i>Over ends. Captain, send next batter (/batting Number).</i>", parse_mode=ParseMode.HTML)
                from plugins.game.team.over_engine import end_over
                await end_over(match)
                return

            match.update({"striker": None})
            if has_client:
                await client.send_message(chat_id, "☝️ <b>WICKET!</b>\n<i>Cleaned up!</i>\n\n🧢 Captain, send next batter: /batting Number", parse_mode=ParseMode.HTML)
            return

        balls_in_over = len(match["current_over_balls"])
        max_overs = match.get("overs", 0)

        if balls_in_over >= 6:
            match.pop("_rotate_next_ball", None)
            match["prompt_dispatched"] = False
            match["bowled"] = False
            match["batted"] = False

            last_ball_runs = match.pop("_last_ball_runs", 0)
            
            if isinstance(last_ball_runs, int) and last_ball_runs % 2 == 0:
                if match.get("striker") and match.get("non_striker"):
                    match["striker"], match["non_striker"] = match["non_striker"], match["striker"]

            if match.get("current_over", 1) >= max_overs:
                from plugins.game.team.over_engine import end_innings
                await end_innings(match)
            else:
                from plugins.game.team.over_engine import end_over
                await end_over(match)
            return

        if match.pop("_rotate_next_ball", False):
            if match.get("striker") and match.get("non_striker"):
                match["striker"], match["non_striker"] = match["non_striker"], match["striker"]

        if has_client:
            try:
                from plugins.utilities.achieve import evaluate_and_unlock_achievements
                newly_unlocked = await evaluate_and_unlock_achievements(actual_striker, match)
                for ach in newly_unlocked:
                    if should_announce_in_group(ach):
                        await announce_achievement_group(client, chat_id, actual_striker, ach, match)
                    else:
                        await announce_achievement_dm(client, actual_striker, ach)
            except Exception as e:
                print("❌ Achievement check failed:", e)

            from plugins.game.team.state import start_first_ball
            await start_first_ball(client, match)

    except Exception as e:
        print("❌ advance_ball ERROR:", e)

    finally:
        match["bowled"] = False
        match["batted"] = False
        match["prompt_dispatched"] = False
        match["phase"] = "LIVE"

        print(
            "🔓 advance_ball EXIT | balls =",
            match.get("total_balls"),
            "| prompt unlocked"
        )

async def end_over(match):
    client = match.get("client")
    if not client:
        print("❌ CRITICAL: client missing in end_over")

        match["bowled"] = False
        match["batted"] = False
        match["prompt_dispatched"] = False
        match["phase"] = "READY"
        return

    chat_id = match.get("chat_id")
    if not chat_id:
        print("❌ chat_id missing in end_over")
        return

    bat_team_key = match.get("batting_team", "A")
    bat_team = match.get("teams", {}).get(bat_team_key)

    if not bat_team:
        print(f"❌ Error: Batting team data missing in end_over for chat {chat_id}")
        return

    if "over_history" not in bat_team:
        bat_team["over_history"] = []
    bat_team["over_history"].append(0)

    completed_over = match.get("current_over", 1)
    bowler_id = match.get("current_bowler")

    last_over_balls = list(match.get("current_over_balls", []))

    match["last_over_bowler_name"] = match.get("user_cache", {}).get(
        bowler_id, "The previous bowler"
    )
    match["last_over_bowler"] = bowler_id

    from plugins.game.team.summaries import build_over_summary
    summary_text = await build_over_summary(client, match)

    match.update({
        "current_bowler": None,
        "current_over": completed_over + 1,
        "ball_in_over": 1,
        "current_over_balls": [],
        "bowled": False,
        "batted": False,
        "last_bowl": None,
        "phase": "READY",
        "prompt_dispatched": False
    })

    players = bat_team.get("players", [])

    def is_alive(uid):
        return (
            uid in players and
            not match["players"].get(uid, {}).get("is_out", False)
        )

    if match.get("striker") and not is_alive(match["striker"]):
        match["striker"] = None

    if match.get("non_striker") and not is_alive(match["non_striker"]):
        match["non_striker"] = None

    if match.get("striker") == match.get("non_striker"):
        alive = [u for u in players if is_alive(u)]
        match["non_striker"] = alive[0] if alive else None

    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE game_players SET role = NULL WHERE game_id = $1",
                match.get("game_id")
            )

            if match.get("striker"):
                await conn.execute(
                    "UPDATE game_players SET role = 'striker' WHERE game_id = $1 AND user_id = $2",
                    match.get("game_id"), match["striker"]
                )

            if match.get("non_striker"):
                await conn.execute(
                    "UPDATE game_players SET role = 'non_striker' WHERE game_id = $1 AND user_id = $2",
                    match.get("game_id"), match["non_striker"]
                )
    except Exception as e:
        print("❌ Role sync error in end_over:", e)

    from plugins.game.team.over_engine import update_game_in_db
    await update_game_in_db(match)

    try:
        buf = await get_graph_buffer(match)
        await client.send_photo(
            chat_id=chat_id,
            photo=buf,
            caption=summary_text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"Graph Error: {e}")
        try:
            await client.send_message(chat_id, summary_text)
        except:
            pass

    try:
        import asyncio, httpx

        await asyncio.sleep(2)

        bat_team = match.get("teams", {}).get(match.get("batting_team"), {})
        runs = bat_team.get("runs", 0)
        wickets = bat_team.get("wickets", 0)

        over_runs = sum(0 if b == "W" else b for b in last_over_balls if isinstance(b, (int, str)))
        over_wkts = last_over_balls.count("W")

        prompt = f"""
You are a cricket commentator AI.
Tone: funny, savage, professional.
Short: 2–3 lines only.

Over number: {completed_over}
Runs this over: {over_runs}
Wickets this over: {over_wkts}
Total score: {runs}/{wickets}

Give a sharp over reaction.
"""

        payload = {
            "model": "meta/llama-3.1-70b-instruct",
            "messages": [
                {"role": "system", "content": "You comment on cricket overs."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.85,
            "max_tokens": 120
        }

        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=15) as ai:
            r = await ai.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                json=payload,
                headers=headers
            )

        ai_text = r.json()["choices"][0]["message"]["content"]

        await client.send_message(
            chat_id,
            f"🧠 <b>OVER ANALYSIS</b>\n────┈┄┄╌╌╌╌┄┄┈────\n{ai_text}",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        print("❌ Over AI analysis failed:", e)

    if completed_over >= match.get("overs", 0):
        from plugins.game.team.over_engine import end_innings
        await end_innings(match)
        return
        
    from plugins.game.team.over_engine import send_next_bowler_prompt
    await send_next_bowler_prompt(match)

async def send_next_bowler_prompt(match):
    client = match.get("client")
    chat_id = match.get("chat_id")

    if not client or not chat_id:
        print("❌ client/chat_id missing in send_next_bowler_prompt")

        match["prompt_dispatched"] = False
        match["phase"] = "READY"
        return

    match["phase"] = "READY"
    
    match["prompt_dispatched"] = False

    last_name = match.get("last_over_bowler_name", "The previous bowler")
    curr_over = match.get("current_over", 1)

    text = (
        f"🏁 <b>Over {curr_over - 1} Complete</b>\n"
        f"────────────────────\n"
        f"👤 <b>Bowling Captain</b>, choose your next bowler!\n"
        f"🔢 Use: /bowling number\n\n"
        f"🚫 <b>Back-to-Back Rule:</b>\n"
        f"╰ {last_name} cannot bowl this over."
    )

    try:
        await client.send_message(
            chat_id,
            text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"Error sending bowler prompt: {e}")

async def end_innings(match):
    client = match.get("client")
    if not client:
        print("❌ CRITICAL: client missing in end_innings")

        match["bowled"] = False
        match["batted"] = False
        match["prompt_dispatched"] = False
        match["phase"] = "READY"
        return

    chat_id = match.get("chat_id")
    game_id = match.get("game_id")
    current_batting_team = match.get("batting_team", "A")

    if not chat_id or not game_id:
        print("❌ chat_id / game_id missing in end_innings")
        return

    if match.get("innings", 1) == 1:

        bat_snapshot = match.get("teams", {}).get(current_batting_team, {}).copy()
        balls_snapshot = bat_snapshot.get("balls", 0)

        match["target"] = bat_snapshot.get("runs", 0) + 1
        match["innings"] = 2

        match["batting_team"], match["bowling_team"] = (
            match.get("bowling_team", "B"),
            match.get("batting_team", "A")
        )
        new_batting_team = match["batting_team"]
        match["phase"] = "READY"

        async with db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE game_players SET role = NULL WHERE game_id = $1",
                    game_id
                )
                await conn.execute(
                    "UPDATE game_players SET is_out = FALSE WHERE game_id = $1 AND team = $2",
                    game_id, new_batting_team
                )

        match.update({
            "partnership": 0,
            "partnership_balls": 0,
            "current_over": 1,
            "ball_in_over": 1,
            "total_balls": 0,
            "striker": None,
            "non_striker": None,
            "current_bowler": None,
            "last_over_bowler": None,
            "last_over_bowler_name": "None",
            "current_over_balls": [],
            "bowled": False,
            "batted": False,
            "prompt_dispatched": False,
            "last_bowl": None
        })

        from plugins.game.team.over_engine import update_game_in_db, build_innings_summary
        await update_game_in_db(match)

        innings_text = await build_innings_summary(client, match)

        try:
            from plugins.utilities.graph import get_graph_buffer
            buf = await get_graph_buffer(match)
            await client.send_photo(
                chat_id=chat_id,
                photo=buf,
                caption=innings_text,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            print(f"Graph Error in end_innings: {e}")
            try:
                await client.send_message(chat_id, innings_text)
            except:
                pass

        try:
            import asyncio, random

            await asyncio.sleep(2)

            runs = bat_snapshot.get("runs", 0)
            wickets = bat_snapshot.get("wickets", 0)
            overs = match.get("overs", 0)
            balls = balls_snapshot

            run_rate = (runs / (balls / 6)) if balls > 0 else 0

            moods = [
                "funny & savage",
                "calm but ruthless",
                "professional with spice"
            ]

            prompt = f"""
You are a cricket analyst.
Tone: {random.choice(moods)}.
Short, punchy, Telegram-friendly.

Innings Summary:
Runs: {runs}
Wickets: {wickets}
Overs: {overs}
Run Rate: {run_rate:.2f}

Give 4–5 lines:
• How the innings went
• One savage observation
• One tactical takeaway for the chase
"""

            analysis = await get_ai_analysis(prompt)

            await client.send_message(
                chat_id,
                (
                    "🧠 <b>AI INNINGS ANALYSIS</b>\n"
                    "────┈┄┄╌╌╌╌┄┄┈────\n\n"
                    f"{analysis}\n\n"
                    "────┈┄┄╌╌╌╌┄┄┈────\n"
                    "✨ Nexora AI"
                ),
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            print("❌ AI Innings Analysis Error:", e)

        await client.send_message(
            chat_id,
            (
                "🚀 <b>Innings Break</b>\n\n"
                f"🎯 Target: <b>{match['target']} runs</b>\n"
                f"🏟 Team {match['batting_team']} needs {match['target']} to win.\n\n"
                "👉 Batting Captain, use /batting number to set openers!"
            ),
            parse_mode=ParseMode.HTML
        )
        return

    from plugins.game.team.over_engine import end_match
    await end_match(match)

async def end_match(match, forced: bool = False):
    import asyncio
    import httpx
    from utils.logger import send_match_log

    client = match.get("client")
    chat_id = match.get("chat_id")
    LOG_GC_ID = -1003692127639

    balls_played = match.get("total_balls", 0)
    early_force_end = forced and balls_played < 6

    if not client or not chat_id:
        print("❌ CRITICAL: client or chat_id missing")
        match["phase"] = "finished"
        return

    teams = match.get("teams", {})
    team_a = teams.get("A", {"runs": 0, "wickets": 0, "players": []})
    team_b = teams.get("B", {"runs": 0, "wickets": 0, "players": []})

    r_a, r_b = team_a["runs"], team_b["runs"]
    w_a, w_b = team_a["wickets"], team_b["wickets"]

    if r_a > r_b:
        winner_key = "A"
        margin = f"won by {r_a - r_b} runs"
    elif r_b > r_a:
        winner_key = "B"
        wickets_left = max(0, len(team_b["players"]) - w_b - 1)
        margin = f"won by {wickets_left} wickets" if wickets_left > 0 else f"won by {r_b - r_a} runs"
    else:
        winner_key = "Tie"
        margin = "Match Tied!"

    if forced:
        winner_key = "No Result"
        margin = "Stopped by host."

    res_title = "🏏 MATCH COMPLETE" if winner_key not in ("Tie", "No Result") else "🤝 MATCH TIED"

    await client.send_message(
        chat_id,
        f"{res_title}\n\n🏆 Team {winner_key} {margin}"
    )

    match["phase"] = "finished"

    try:
        from plugins.game.team.scorecard import save_match_stats
        asyncio.create_task(save_match_stats(match, winner_key))
    except Exception as e:
        print("Stats Save Error:", e)

    try:
        log_match = {
            "game_id": str(match.get("game_id")),
            "chat_id": chat_id,
            "host_id": match.get("host_id"),
            "host_name": match.get("host_name", "Unknown")
        }

        await send_match_log(
            client,
            "🏁 MATCH COMPLETED",
            log_match,
            "Match completed and stats saved."
        )
    except Exception as e:
        print("Logger Error:", e)

    from plugins.game.team import ACTIVE_MATCHES
    ACTIVE_MATCHES.pop(chat_id, None)

    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE games SET status = 'ended' WHERE game_id = $1",
                match.get("game_id")
            )
    except Exception as e:
        print("❌ DB update failed:", e)

    print(f"✅ Match {match.get('game_id')} cleanup done")

    async def post_match_extras():
        try:
            if not early_force_end and winner_key in ("A", "B"):
                players = match.get("players", {})
                winning_players = teams[winner_key].get("players", [])

                best_id, best_score = None, -1
                for uid in winning_players:
                    p = players.get(uid, {})
                    score = p.get("runs", 0) + (p.get("wickets", 0) * 25)
                    if score > best_score:
                        best_score = score
                        best_id = uid

                if best_id:
                    p = players[best_id]
                    name = match.get("user_cache", {}).get(best_id, "Player")

                    prompt = f"""
Player: {name}
Runs: {p.get('runs',0)}
Wickets: {p.get('wickets',0)}

Give a short 2–3 line cricket analysis.
"""

                    payload = {
                        "model": "meta/llama-3.1-70b-instruct",
                        "messages": [
                            {"role": "system", "content": "You analyze cricket matches briefly."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 80
                    }

                    headers = {
                        "Authorization": f"Bearer {NVIDIA_API_KEY}",
                        "Content-Type": "application/json"
                    }

                    analysis = ""
                    try:
                        async with httpx.AsyncClient(timeout=8) as ai:
                            r = await ai.post(NVIDIA_ENDPOINT, json=payload, headers=headers)
                            analysis = r.json()["choices"][0]["message"]["content"]
                    except Exception:
                        analysis = "Clutch performance when it mattered most."

                    potm_text = (
                        "🏅 PLAYER OF THE MATCH\n"
                        "──────────────\n"
                        f"👤 {name}\n"
                        f"🏏 Runs: {p.get('runs',0)}\n"
                        f"🎯 Wickets: {p.get('wickets',0)}\n\n"
                        f"{analysis}"
                    )

                    await client.send_message(chat_id, potm_text)
                    await client.send_message(LOG_GC_ID, potm_text)

            from plugins.game.team.summaries import build_match_summary
            summary_text = await build_match_summary(client, match, winner_key)

            caption = (
                f"{res_title}\n\n"
                f"🏆 Team {winner_key} {margin}\n\n"
                f"{summary_text}"
            )

            try:
                from plugins.utilities.graph import get_graph_buffer
                buf = await get_graph_buffer(match)

                await client.send_photo(chat_id, photo=buf, caption=caption)
                await client.send_photo(LOG_GC_ID, photo=buf, caption=caption)
            except Exception:
                await client.send_message(chat_id, caption)
                await client.send_message(LOG_GC_ID, caption)

        except Exception as e:
            print("❌ Post-match task error:", e)

    asyncio.create_task(post_match_extras())
