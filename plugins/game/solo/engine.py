import asyncio
import random
import html
import io
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

from plugins.game.team import ACTIVE_MATCHES
from plugins.game.solo import get_next_solo_bowler, build_solo_score_text, PLAYZONE_BTN

BATTER_LINES = {
    50: [
        "{p} raises the bat 🏏 Half-century loaded!",
        "Fifty up! {p} is cooking now 🔥",
        "{p} casually reaches 50 like it's a warm-up session.",
        "Scoreboard ticking. 50 for {p}!",
        "{p} hits 50 and the bowlers are questioning life choices 😂",
        "FIFTY! {p} is absolutely locked in right now 🔒",
        "What an innings! {p} brings up the half-ton 🏏",
        "Classy 50 from {p}. The pitch is their playground 👑",
    ],
    100: [
        "CENTURY! 💯 {p} has rewritten the script.",
        "{p} goes full beast mode 💥 Hundred on the board.",
        "Standing ovation 👏 {p} brings up a ton.",
        "100 for {p}! Bowlers checking if this is a nightmare.",
        "Bowling unit officially deleted. {p} hits 100.",
        "THE CENTURY IS UP! {p} is in another dimension right now 🌌",
        "3 figures! {p} is unstoppable today — absolutely ruthless 😤",
        "From 50 to 100, {p} didn't even break a sweat 🧊",
    ],
    150: [
        "150! This is domination by {p}.",
        "{p} refuses to stop. 150 and counting 👑",
        "At this point {p} should just keep the bat forever.",
        "INSANE! {p} blazes past 150! Where is this ending? 🚀",
        "150 for {p}! Someone call the coaches — this is historic 📜",
    ],
    250: [
        "HISTORY ALERT 🚨 {p} smashes 250!",
        "Unreal innings… {p} hits 250 😵‍💫",
        "Statistical insanity. {p} posts 250.",
        "250!! We're not worthy. {p} is a living legend 🏆",
        "This can't be real. {p} scores 250 in a solo match 🤯",
    ],
}

BOWLER_LINES = {
    3: [
        "{p} strikes thrice 🎯 3-wicket haul!",
        "Bowling clinic! {p} picks up 3.",
        "{p} collecting wickets like Pokémon cards 😂",
        "Three down! {p} is on a rampage 💀",
        "Hat-trick territory! 3 wickets for {p} 👀",
        "TRIPLE STRIKE! {p} is cleaning up the innings 🧹",
    ],
    5: [
        "FIVE-FOR! 🖐️ {p} demolishes the batting.",
        "Bowling royalty 👑 5 wickets for {p}.",
        "Complete destruction. 5 wickets for {p}.",
        "The batters have no answer! FIVE-FOR for {p} 🏏💥",
        "Legendary spell! {p} takes 5 wickets! 🔥",
        "This is bowling at its finest. 5 wickets for {p} 🎯",
    ],
}


def _mention(match, uid):
    name = match.get("user_cache", {}).get(uid, "Player")
    return f"<a href='tg://user?id={uid}'>{html.escape(name)}</a>"


async def _safe_send_msg(client, chat_id, text, parse_mode=ParseMode.HTML, reply_markup=None):
    try:
        return await client.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            return await client.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception:
            pass
    except Exception as e:
        print(f"send_message error: {e}")
    return None


async def _send_achievement(client, chat_id, key, caption):
    from Assets.files import ACHIEVE_VIDEOS, ACHIEVE_IMG
    videos = ACHIEVE_VIDEOS.get(key, [])
    if videos:
        file_id = random.choice(videos)
        try:
            await client.send_video(chat_id=chat_id, video=file_id,
                                    caption=caption, parse_mode=ParseMode.HTML)
            return
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            pass
        try:
            await client.send_animation(chat_id=chat_id, animation=file_id,
                                        caption=caption, parse_mode=ParseMode.HTML)
            return
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            pass
    try:
        await client.send_photo(chat_id=chat_id, photo=ACHIEVE_IMG,
                                caption=caption, parse_mode=ParseMode.HTML)
        return
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass
    await _safe_send_msg(client, chat_id, caption)


async def solo_advance_ball(match, result, credit_bowler=True):
    client = match.get("client")
    chat_id = match.get("chat_id")
    if not client or not chat_id:
        return

    batter_id = match.get("current_batter")
    bowler_id = match.get("current_bowler")
    stats = match.get("player_stats", {})

    batter_stats = stats.setdefault(batter_id, _blank_stats())
    bowler_stats = stats.setdefault(bowler_id, _blank_stats()) if bowler_id else {}

    timeouts = match.get("timeouts", {})
    timeouts.get("bowler", {})["fails"] = 0
    timeouts.get("batter", {})["fails"] = 0

    try:
        if result == "W":
            batter_stats["balls_faced"] += 1
            batter_stats["is_out"] = True
            batter_stats["batting_balls"].append("W")

            if credit_bowler and bowler_id and bowler_stats:
                bowler_stats["wickets"] += 1
                bowler_stats["balls_bowled"] += 1
                bowler_stats["bowling_balls"].append("W")
                await _check_bowler_achievements(client, chat_id, match, bowler_id, bowler_stats)

            match["total_balls"] += 1
            match["total_wickets"] += 1
            match["balls_in_spell"] = match.get("balls_in_spell", 0) + 1

            await _next_batter_or_end(match)

        else:
            runs = int(result)
            batter_stats["runs"] += runs
            batter_stats["balls_faced"] += 1
            batter_stats["batting_balls"].append(runs)
            if runs == 4:
                batter_stats["fours_count"] += 1
            elif runs == 6:
                batter_stats["sixes_count"] += 1

            if bowler_id and bowler_stats:
                bowler_stats["runs_conceded"] += runs
                bowler_stats["balls_bowled"] += 1
                bowler_stats["bowling_balls"].append(runs)

            match["total_runs"] += runs
            match["total_balls"] += 1
            match["balls_in_spell"] = match.get("balls_in_spell", 0) + 1

            await _check_batter_achievements(client, chat_id, match, batter_id, batter_stats)

            if match.get("balls_in_spell", 0) >= 3:
                await _rotate_bowler(client, match)
            else:
                await _next_ball(client, match)

    except Exception as e:
        print(f"solo_advance_ball error: {e}")
    finally:
        match["bowled"] = False
        match["batted"] = False
        match["prompt_dispatched"] = False
        match["last_bowl"] = None


def _blank_stats():
    return {
        "runs": 0,
        "balls_faced": 0,
        "is_out": False,
        "batting_balls": [],
        "bowling_balls": [],
        "wickets": 0,
        "runs_conceded": 0,
        "balls_bowled": 0,
        "fours_count": 0,
        "sixes_count": 0,
    }


async def _rotate_bowler(client, match):
    chat_id = match["chat_id"]
    match["balls_in_spell"] = 0
    next_bowler = get_next_solo_bowler(match)
    match["current_bowler"] = next_bowler
    if next_bowler:
        name = match.get("user_cache", {}).get(next_bowler, "Player")
        await _safe_send_msg(client, chat_id, f"🎯 Hey {name}, now you're bowling!")
        await _next_ball(client, match)
    else:
        await _end_solo_match(match)


async def _next_batter_or_end(match):
    client = match.get("client")
    chat_id = match.get("chat_id")
    players = match["players"]
    current_batter = match.get("current_batter")

    try:
        current_idx = players.index(current_batter)
    except ValueError:
        await _end_solo_match(match)
        return

    next_idx = current_idx + 1
    if next_idx >= len(players):
        await _end_solo_match(match)
        return

    next_batter = players[next_idx]
    match["current_batter"] = next_batter

    current_bowler = match.get("current_bowler")
    if current_bowler == next_batter:
        match["balls_in_spell"] = 0
        new_bowler = get_next_solo_bowler(match)
        match["current_bowler"] = new_bowler
        bname = match.get("user_cache", {}).get(new_bowler, "Player")
        await _safe_send_msg(
            client, chat_id,
            f"🔄 Bowler swap! {bname} now bowling (can't bat & bowl same player).",
        )

    new_batter_name = match.get("user_cache", {}).get(next_batter, "Player")
    await _safe_send_msg(client, chat_id, f"🎉 Hey {new_batter_name}, now you're batting!")
    await _next_ball(client, match)


async def _next_ball(client, match):
    from plugins.game.solo.state import send_solo_ball_prompt
    match["prompt_dispatched"] = False
    await send_solo_ball_prompt(client, match)


async def _end_solo_match(match, forced=False):
    client = match.get("client")
    chat_id = match.get("chat_id")
    if not client or not chat_id:
        match["phase"] = "finished"
        return

    match["phase"] = "finished"

    try:
        from plugins.game.solo.scorecard import build_solo_end_card
        card_buf = build_solo_end_card(match)
        caption = _build_final_scorecard_text(match)
        try:
            await client.send_photo(
                chat_id=chat_id, photo=card_buf,
                caption=caption, parse_mode=ParseMode.HTML,
                reply_markup=PLAYZONE_BTN,
            )
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await client.send_photo(
                chat_id=chat_id, photo=card_buf,
                caption=caption, parse_mode=ParseMode.HTML,
                reply_markup=PLAYZONE_BTN,
            )
    except Exception as e:
        print(f"Solo end card error: {e}")
        try:
            await _safe_send_msg(
                client, chat_id,
                _build_final_scorecard_text(match),
                reply_markup=PLAYZONE_BTN,
            )
        except Exception:
            pass

    try:
        from database.games import end_game as close_db_game
        await close_db_game(chat_id)
    except Exception as e:
        print(f"Solo end DB error: {e}")

    asyncio.create_task(_save_solo_stats(match))
    ACTIVE_MATCHES.pop(chat_id, None)
    print(f"✅ Solo match in {chat_id} ended{'(forced)' if forced else ''}.")


async def _save_solo_stats(match):
    stats = match.get("player_stats", {})
    try:
        from database.connection import db
        pool = await db.ensure_pool() or db.pool
        if not db.pool:
            return
        async with db.pool.acquire() as conn:
            for uid, p in stats.items():
                runs = p.get("runs", 0)
                wickets = p.get("wickets", 0)
                is_out = 1 if p.get("is_out") else 0
                fours = p.get("fours_count", 0)
                sixes = p.get("sixes_count", 0)
                b_faced = p.get("balls_faced", 0)
                b_bowled = p.get("balls_bowled", 0)
                r_conceded = p.get("runs_conceded", 0)
                is_50 = 1 if 50 <= runs < 100 else 0
                is_100 = 1 if runs >= 100 else 0
                is_duck = 1 if runs == 0 and is_out else 0

                await conn.execute(
                    """
                    INSERT INTO user_stats (
                        user_id, matches, wins, losses, runs, wickets,
                        balls_faced, balls_bowled, runs_conceded, fours, sixes,
                        moms, centuries, fifties, ducks
                    )
                    VALUES ($1, 1, 0, $2, $3, $4, $5, $6, $7, $8, $9, 0, $10, $11, $12)
                    ON CONFLICT (user_id) DO UPDATE SET
                        matches = user_stats.matches + 1,
                        runs = user_stats.runs + $3,
                        wickets = user_stats.wickets + $4,
                        balls_faced = user_stats.balls_faced + $5,
                        balls_bowled = user_stats.balls_bowled + $6,
                        runs_conceded = user_stats.runs_conceded + $7,
                        fours = user_stats.fours + $8,
                        sixes = user_stats.sixes + $9,
                        centuries = user_stats.centuries + $10,
                        fifties = user_stats.fifties + $11,
                        ducks = user_stats.ducks + $12
                    """,
                    uid, is_out, runs, wickets, b_faced, b_bowled,
                    r_conceded, fours, sixes, is_100, is_50, is_duck,
                )
    except Exception as e:
        print(f"Solo stats save error: {e}")


def _calc_sr(runs, balls):
    if balls == 0:
        return "0.0"
    return f"{(runs / balls * 100):.1f}"


def _build_final_scorecard_text(match):
    players = match.get("players", [])
    stats = match.get("player_stats", {})
    user_cache = match.get("user_cache", {})

    top_scorer_id, top_runs = None, -1
    top_wickets_id, top_wickets = None, -1

    for uid in players:
        p = stats.get(uid, {})
        if p.get("runs", 0) > top_runs:
            top_runs = p["runs"]
            top_scorer_id = uid
        if p.get("wickets", 0) > top_wickets:
            top_wickets = p["wickets"]
            top_wickets_id = uid

    lines = ["≪━─━─━◈ <b>Sᴏʟᴏ Fɪɴᴀʟ Sᴄᴏʀᴇ</b> ◈━─━─━≫\n"]

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

    lines.append("────┈┄┄╌╌╌╌┄┄┈────")

    if top_scorer_id:
        ts_name = user_cache.get(top_scorer_id, "Player")
        ts_balls = stats.get(top_scorer_id, {}).get("balls_faced", 0)
        lines.append(f"🏏 <b>Top Scorer:</b> {ts_name} — {top_runs} ({ts_balls})")
    if top_wickets_id and top_wickets > 0:
        tw_name = user_cache.get(top_wickets_id, "Player")
        lines.append(f"🎯 <b>Best Bowler:</b> {tw_name} — {top_wickets} wkt(s)")

    total_runs = match.get("total_runs", 0)
    total_balls = match.get("total_balls", 0)
    overs = f"{total_balls // 6}.{total_balls % 6}"
    lines.append(f"╰⊚ <b>Total:</b> {total_runs} in {overs} overs")
    lines.append("✨ GG! | ʟᴇɢᴀᴄʏ ᴄʀɪᴄᴋᴇᴛ")

    return "\n\n".join(lines)


async def _check_batter_achievements(client, chat_id, match, batter_id, p):
    announced = match.setdefault("announced_achievements", {}).setdefault("batting", {})
    batter_announced = announced.setdefault(batter_id, set())
    runs = p.get("runs", 0)
    name = _mention(match, batter_id)
    for milestone, lines in BATTER_LINES.items():
        if runs >= milestone and milestone not in batter_announced:
            batter_announced.add(milestone)
            text = random.choice(lines).format(p=name)
            caption = f"🏆 <b>Achievement!</b>\n<i>{text}</i>"
            asyncio.create_task(_send_achievement(client, chat_id, milestone, caption))


async def _check_bowler_achievements(client, chat_id, match, bowler_id, p):
    announced = match.setdefault("announced_achievements", {}).setdefault("bowling", {})
    bowl_announced = announced.setdefault(bowler_id, set())
    wkts = p.get("wickets", 0)
    name = _mention(match, bowler_id)
    for milestone, lines in BOWLER_LINES.items():
        if wkts >= milestone and milestone not in bowl_announced:
            bowl_announced.add(milestone)
            text = random.choice(lines).format(p=name)
            caption = f"🎯 <b>Achievement!</b>\n<i>{text}</i>"
            asyncio.create_task(_send_achievement(client, chat_id, milestone, caption))
