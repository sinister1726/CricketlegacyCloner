"""
/records — Group-specific all-time records.

Usage (in a group):  /records
"""

import html
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from database.group_records import get_group_records


def _link(uid: int, name: str) -> str:
    return f"<a href='tg://user?id={uid}'>{html.escape(name)}</a>"


def _sr_fmt(sr: float) -> str:
    return f"{sr:.1f}"


def _balls_to_overs(balls: int) -> str:
    return f"{balls // 6}.{balls % 6}"


async def build_records_text(chat_id: int, chat_title: str) -> str:
    r = await get_group_records(chat_id)

    if not r or not any(
        k in r for k in (
            "highest_score", "most_sixes_match", "most_fours_match",
            "best_bowling", "highest_team_total",
        )
    ):
        return (
            "📭 <b>No records yet!</b>\n\n"
            "Play some matches in this group and records will appear here. 🏏"
        )

    lines = [
        f"🏆 <b>{html.escape(chat_title)} — ALL-TIME RECORDS</b>",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    # ── Batting records ──────────────────────────────────────────────────
    lines.append("\n🏏 <b>BATTING</b>")

    hs = r.get("highest_score")
    if hs:
        sr_note = f"  SR {_sr_fmt(hs.get('sr', 0))}" if hs.get("sr") else ""
        lines.append(
            f"🔥 Highest Score:  {_link(hs['uid'], hs['name'])}  "
            f"<b>{hs['runs']}</b> ({hs.get('balls', '?')}b{sr_note})  "
            f"<i>{hs.get('date', '')}</i>"
        )

    sixes = r.get("most_sixes_match")
    if sixes:
        lines.append(
            f"6️⃣ Most 6s/Match:  {_link(sixes['uid'], sixes['name'])}  "
            f"<b>{sixes['count']} sixes</b>  "
            f"<i>{sixes.get('date', '')}</i>"
        )

    fours = r.get("most_fours_match")
    if fours:
        lines.append(
            f"4️⃣ Most 4s/Match:  {_link(fours['uid'], fours['name'])}  "
            f"<b>{fours['count']} fours</b>  "
            f"<i>{fours.get('date', '')}</i>"
        )

    bsr = r.get("best_sr_match")
    if bsr:
        lines.append(
            f"⚡ Best SR (≥15b): {_link(bsr['uid'], bsr['name'])}  "
            f"<b>{_sr_fmt(bsr['sr'])}</b>  ({bsr['runs']}/{bsr['balls']}b)  "
            f"<i>{bsr.get('date', '')}</i>"
        )

    # ── Bowling records ──────────────────────────────────────────────────
    lines.append("\n🎯 <b>BOWLING</b>")

    bb = r.get("best_bowling")
    if bb:
        overs = _balls_to_overs(bb.get("balls", 0))
        lines.append(
            f"🏆 Best Figures:   {_link(bb['uid'], bb['name'])}  "
            f"<b>{bb['wickets']}/{bb['runs_conceded']}</b> ({overs} ov)  "
            f"<i>{bb.get('date', '')}</i>"
        )

    hat_tricks = r.get("hat_tricks", [])
    if hat_tricks:
        # Deduplicate by uid for display (show count if multiple)
        ht_counts: dict = {}
        for ht in hat_tricks:
            uid  = ht["uid"]
            name = ht["name"]
            ht_counts[uid] = (name, ht_counts.get(uid, (name, 0))[1] + 1)

        ht_parts = []
        for uid, (name, cnt) in ht_counts.items():
            suffix = f" ×{cnt}" if cnt > 1 else ""
            ht_parts.append(f"{_link(uid, name)}{suffix}")
        lines.append(f"🎩 Hat-Tricks:     {',  '.join(ht_parts)}")

    # ── Team records ─────────────────────────────────────────────────────
    ht = r.get("highest_team_total")
    if ht:
        lines.append("\n🏟️ <b>TEAM</b>")
        overs = _balls_to_overs(ht.get("balls", 0))
        lines.append(
            f"📈 Highest Total:  <b>{html.escape(ht.get('team_name', 'Team'))}</b>  "
            f"<b>{ht['runs']}</b> ({overs} ov)  "
            f"<i>{ht.get('date', '')}</i>"
        )

    # ── Milestone counters ────────────────────────────────────────────────
    total_50s  = r.get("total_fifties", 0)
    total_100s = r.get("total_centuries", 0)
    total_6s   = r.get("total_sixes", 0)
    total_4s   = r.get("total_fours", 0)
    total_hts  = len(hat_tricks)

    if any([total_50s, total_100s, total_6s, total_4s, total_hts]):
        lines.append("\n💫 <b>GROUP MILESTONES</b>")
        parts = []
        if total_50s:  parts.append(f"⭐ {total_50s} Fifties")
        if total_100s: parts.append(f"💯 {total_100s} Centuries")
        if total_6s:   parts.append(f"6️⃣ {total_6s:,} Sixes")
        if total_4s:   parts.append(f"4️⃣ {total_4s:,} Fours")
        if total_hts:  parts.append(f"🎩 {total_hts} Hat-Tricks")
        lines.append("  •  ".join(parts))

    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


@Client.on_message(filters.command("records") & filters.group)
async def records_cmd(client: Client, message: Message):
    chat_id    = message.chat.id
    chat_title = message.chat.title or "This Group"

    await message.reply_text(
        await build_records_text(chat_id, chat_title),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
