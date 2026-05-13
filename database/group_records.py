"""
Group-specific records — best performances ever achieved in a particular group.

Records tracked:
  Batting  : highest_score, most_sixes_match, most_fours_match, best_sr_match
  Bowling  : best_bowling, hat_tricks (list)
  Team     : highest_team_total
  Milestones: total_fifties, total_centuries, total_sixes, total_fours
"""

from datetime import datetime
from database.connection import db


def _now() -> str:
    return datetime.utcnow().strftime("%d %b %Y")


async def update_group_records(match: dict, players: dict, winner_team: str):
    chat_id    = match.get("chat_id")
    user_cache = match.get("user_cache", {})
    teams      = match.get("teams", {})

    if not chat_id:
        return

    await db.ensure_pool()
    col     = db.db["group_records"]
    current = await col.find_one({"chat_id": chat_id}) or {}

    set_ops = {}
    inc_ops = {}
    push_ops = {}

    for uid, p in players.items():
        uid  = int(uid) if isinstance(uid, str) else uid
        name = user_cache.get(uid, "Player")
        runs       = p.get("runs", 0)
        sixes      = p.get("sixes_count", 0)
        fours      = p.get("fours_count", 0)
        wickets    = p.get("wickets", 0)
        rc         = p.get("runs_conceded", 0)
        bf         = p.get("balls_faced", 0)
        bb         = p.get("balls_bowled", 0)
        is_50      = 50 <= runs < 100
        is_100     = runs >= 100

        # ── Highest score ────────────────────────────────────────────────
        cur_hs = current.get("highest_score", {}).get("runs", -1)
        if runs > cur_hs:
            sr = round((runs / bf) * 100, 1) if bf else 0
            set_ops["highest_score"] = {
                "uid": uid, "name": name, "runs": runs,
                "balls": bf, "sr": sr, "date": _now(),
            }

        # ── Most sixes in a match ─────────────────────────────────────────
        if sixes > current.get("most_sixes_match", {}).get("count", -1):
            set_ops["most_sixes_match"] = {
                "uid": uid, "name": name, "count": sixes,
                "runs": runs, "date": _now(),
            }

        # ── Most fours in a match ─────────────────────────────────────────
        if fours > current.get("most_fours_match", {}).get("count", -1):
            set_ops["most_fours_match"] = {
                "uid": uid, "name": name, "count": fours,
                "runs": runs, "date": _now(),
            }

        # ── Best strike rate (min 15 balls faced) ─────────────────────────
        if bf >= 15 and runs > 0:
            sr = round((runs / bf) * 100, 1)
            if sr > current.get("best_sr_match", {}).get("sr", -1):
                set_ops["best_sr_match"] = {
                    "uid": uid, "name": name, "sr": sr,
                    "runs": runs, "balls": bf, "date": _now(),
                }

        # ── Best bowling figures ───────────────────────────────────────────
        cur_bw = current.get("best_bowling", {})
        cur_w  = cur_bw.get("wickets", -1)
        cur_rc = cur_bw.get("runs_conceded", 9999)
        if wickets > 0 and (wickets > cur_w or (wickets == cur_w and rc < cur_rc)):
            set_ops["best_bowling"] = {
                "uid": uid, "name": name, "wickets": wickets,
                "runs_conceded": rc, "balls": bb, "date": _now(),
            }

        # ── Hat-tricks (3 consecutive wickets in bowling_balls) ───────────
        bowling_balls = p.get("bowling_balls", [])
        for i in range(len(bowling_balls) - 2):
            if bowling_balls[i] == "W" and bowling_balls[i+1] == "W" and bowling_balls[i+2] == "W":
                push_ops.setdefault("hat_tricks", []).append(
                    {"uid": uid, "name": name, "date": _now()}
                )
                break  # one hat-trick per bowler per match

        # ── Milestone counters ────────────────────────────────────────────
        if is_50:
            inc_ops["total_fifties"] = inc_ops.get("total_fifties", 0) + 1
        if is_100:
            inc_ops["total_centuries"] = inc_ops.get("total_centuries", 0) + 1
        if sixes:
            inc_ops["total_sixes"] = inc_ops.get("total_sixes", 0) + sixes
        if fours:
            inc_ops["total_fours"] = inc_ops.get("total_fours", 0) + fours

    # ── Highest team total ────────────────────────────────────────────────
    for team_key, team in teams.items():
        t_runs  = team.get("runs", 0)
        t_balls = team.get("balls", 0)
        if t_runs > current.get("highest_team_total", {}).get("runs", -1):
            team_name = team.get("name") or f"Team {team_key}"
            set_ops["highest_team_total"] = {
                "team_key": team_key, "team_name": team_name,
                "runs": t_runs, "balls": t_balls, "date": _now(),
            }

    update = {}
    if set_ops:
        update["$set"] = set_ops
    if inc_ops:
        update["$inc"] = inc_ops
    for field, items in push_ops.items():
        update.setdefault("$push", {})[field] = {"$each": items}

    if update:
        await col.update_one({"chat_id": chat_id}, update, upsert=True)


async def get_group_records(chat_id: int) -> dict:
    await db.ensure_pool()
    return await db.db["group_records"].find_one({"chat_id": chat_id}) or {}
