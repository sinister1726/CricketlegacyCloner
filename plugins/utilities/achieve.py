import re
import json
import random
import httpx
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from database.connection import db
from Assets.files import ACHIEVE_IMG
import time

# ───────────── MAINTENANCE SYSTEM ─────────────

OWNER_ID = 8294062042

# Global maintenance state
MAINTENANCE_MODE = {
    "status": False,
    "reason": "Bot is upgrading..."
}


# ───────────── DECORATOR ─────────────
def maintenance(func):
    async def wrapper(client, message, *args, **kwargs):
        if MAINTENANCE_MODE["status"]:

            text = f"""
╭━━━〔 🚧 𝗕𝗢𝗧 𝗨𝗡𝗗𝗘𝗥 𝗠𝗔𝗜𝗡𝗧𝗘𝗡𝗔𝗡𝗖𝗘 🚧 〕━━━╮

✨ Our services are temporarily unavailable.

📌 **Reason:**
{MAINTENANCE_MODE['reason']}

🔔 Please stay connected for updates.

📢 Contact:
[ʟᴇɢᴀᴄʏ ᴘʟᴀʏᴢᴏɴᴇ 🏏](https://t.me/+joF1bCfiMT9jMzVh)

"""

            return await message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )

        return await func(client, message, *args, **kwargs)

    return wrapper


# ───────────── COMMAND ─────────────
@Client.on_message(filters.command("maintenance") & filters.private)
async def toggle_maintenance(client, message: Message):

    if message.from_user.id != OWNER_ID:
        return await message.reply_text("🚫 Only Owner can use this command.")

    args = message.text.split(maxsplit=2)

    if len(args) < 2:
        return await message.reply_text(
            "Usage:\n"
            "`/maintenance on reason`\n"
            "`/maintenance off`",
            parse_mode=ParseMode.MARKDOWN
        )

    action = args[1].lower()

    if action == "on":
        reason = args[2] if len(args) > 2 else "Bot is under maintenance."

        MAINTENANCE_MODE["status"] = True
        MAINTENANCE_MODE["reason"] = reason

        return await message.reply_text(
            f"✅ Maintenance Mode Enabled.\n\n📌 Reason:\n{reason}"
        )

    elif action == "off":
        MAINTENANCE_MODE["status"] = False
        MAINTENANCE_MODE["reason"] = "Bot is upgrading..."

        return await message.reply_text("✅ Maintenance Mode Disabled.")

    else:
        return await message.reply_text("Invalid option. Use on/off.")

# ───────────────── CONFIG ─────────────────
NVIDIA_API_KEY = "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"
PAGE_SIZE = 6

async def random_achievement_hint(conn, user_id: int):
    row = await conn.fetchrow("""
        SELECT title, description
        FROM achievements a
        WHERE NOT EXISTS (
            SELECT 1 FROM user_achievements ua
            WHERE ua.user_id=$1 AND ua.achievement_id=a.id
        )
        ORDER BY RANDOM()
        LIMIT 1
    """, user_id)

    if not row:
        return "🏆 You’ve unlocked everything. Absolute legend."

    return (
        "🎯 <b>Hint Unlocked</b>\n\n"
        f"🏆 <b>{row['title']}</b>\n"
        f"📖 {row['description']}\n\n"
        "Keep playing to unlock it!"
    )

async def ai_generate_condition(title: str, description: str):
    prompt = f"""
You are a cricket game logic engine.

Analyze this achievement and decide how progress should be tracked.

Achievement:
Title: {title}
Description: {description}

Return STRICT JSON ONLY in this exact format:
{{
  "scope": "career|match|innings",
  "stat": "runs|wickets|maidens|matches|partnership|catches|sixes|fours",
  "target": number
}}

Rules:
- Scope must match description meaning
- Target must be realistic
- No explanation
- JSON only
"""
    raw = await _ai(prompt, temp=0.2, tokens=120)
    return json.loads(raw)


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

async def safe_callback_answer(cb, text: str):
    MAX = 180  # stay safely under Telegram limit
    if len(text) <= MAX:
        await cb.answer(text, show_alert=True)
    else:
        await cb.answer("🎁 Surprise incoming…", show_alert=False)
        await cb.message.reply_text(text)


# ───────────────── AI CORE ─────────────────
async def _ai(prompt, temp=0.9, tokens=180):
    payload = {
        "model": "meta/llama3-70b-instruct",  # safer name
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temp,
        "max_tokens": tokens
    }

    async with httpx.AsyncClient(timeout=40) as ai:
        r = await ai.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Content-Type": "application/json"
            }
        )

    # 🔥 HARD DEBUG
    if r.status_code != 200:
        raise RuntimeError(
            f"NVIDIA API Error {r.status_code}:\n{r.text[:800]}"
        )

    data = r.json()

    if "choices" not in data:
        raise RuntimeError(
            f"Malformed AI response:\n{json.dumps(data, indent=2)[:800]}"
        )

    return data["choices"][0]["message"]["content"]

# ───────────────── AI ROAST ─────────────────
async def ai_roast_user(name, brutal=False):
    tone = "EXTREMELY savage, humiliating, esports-toxic" if brutal else "playful savage"
    prompt = f"""
Roast a cricket player.
Tone: {tone}
Name: {name}
2–3 lines max.
"""
    return (await _ai(prompt, temp=1.0, tokens=120))[:500]

# ───────────────── AI CONGRATS ─────────────────
async def ai_congrats(name, ach):
    moods = ["funny", "savage", "wholesome", "toxic esports"]
    prompt = f"""
Congratulate a cricket player.
Tone: {random.choice(moods)}.
2–3 lines.

Player: {name}
Achievement: {ach['title']}
"""
    return await _ai(prompt)



    
# ───────────────── DYNAMIC ACHIEVEMENT (AI GENERATED) ─────────────────
async def generate_dynamic_achievement(user_id: int):
    prompt = """
Create a UNIQUE cricket achievement.
Return STRICT JSON only:

{
  "title": "...",
  "description": "...",
  "condition": {
    "type": "batting|bowling|team",
    "runs_gte": number,
    "wickets_gte": number
  }
}
"""
    raw = await _ai(prompt, temp=0.95)
    data = json.loads(raw)

    async with db.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO achievements (code,title,description,condition,rarity,is_dynamic)
            VALUES ($1,$2,$3,$4,'legendary',TRUE)
            ON CONFLICT DO NOTHING
        """,
        f"DYN_{user_id}_{random.randint(1000,9999)}",
        data["title"],
        data["description"],
        data["condition"]
        )


    
    
# ───────────────── /ACHIEVEMENTS COMMAND ─────────────────
@Client.on_message(filters.command("achievements"))
async def achievements_cmd(client, message):
    user = message.from_user
    await evaluate_and_unlock_achievements(user.id)

    async with db.pool.acquire() as conn:
        earned = await conn.fetch("""
            SELECT a.title
            FROM user_achievements ua
            JOIN achievements a ON a.id=ua.achievement_id
            WHERE ua.user_id=$1
        """, user.id)

    if not earned:
        caption = await ai_roast_user(user.first_name, brutal=True)
    else:
        caption = (
            f"🏆 <b>{user.first_name}'s Achievements</b>\n\n" +
            "\n".join(f"✅ {a['title']}" for a in earned[:10]) +
            f"\n\n📦 Total Unlocked: <b>{len(earned)}</b>"
        )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 All Achievements", callback_data="ach_page_0")],
        [
            InlineKeyboardButton("✨ Surprise Me", callback_data="ach_surprise"),
            InlineKeyboardButton("❌ Close", callback_data="ach_close")
        ]
    ])

    await client.send_photo(
        message.chat.id,
        ACHIEVE_IMG,
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )

# ───────────────── PAGINATION BUILDER ─────────────────
async def build_page(conn, user_id: int, page: int, match=None):
    offset = page * PAGE_SIZE

    rows = await conn.fetch("""
        SELECT a.*,
               ua.user_id IS NOT NULL AS achieved
        FROM achievements a
        LEFT JOIN user_achievements ua
          ON ua.achievement_id = a.id AND ua.user_id = $1
        ORDER BY a.condition->>'scope', a.id
        LIMIT $2 OFFSET $3
    """, user_id, PAGE_SIZE, offset)

    stats = await conn.fetchrow(
        "SELECT * FROM user_stats WHERE user_id=$1",
        user_id
    ) or {}

    total = await conn.fetchval("SELECT COUNT(*) FROM achievements")

    text = f"🏆 <b>All Achievements</b>\n"
    text += f"📦 Total: <b>{total}</b>\n\n"

    for a in rows:
        cond = normalize_condition(a["condition"])
        scope = cond.get("scope", "unknown")

        icon = "🧧" if a["achieved"] else "⬜"

        cur, tgt = get_progress(a, stats, match or {})

        text += (
            f"{icon} <b>{a['title']}</b>\n"
            f"📖 {a['description']}\n"
            f"📊 Progress: <b>{cur} / {tgt}</b>\n"
            f"🏷️ {a['rarity']} | {scope}\n\n"
        )

    return text


@Client.on_callback_query(filters.regex("^ach_"))
async def achievements_callback(client, cb):
    await cb.answer()  # 👈 INSTANT ACK (fixes lag)

    data = cb.data

    if data == "ach_close":
        return await cb.message.delete()

    if data == "ach_surprise":
        await cb.answer("🎁 Surprise!", show_alert=False)

        async with db.pool.acquire() as conn:
            text = await random_achievement_hint(conn, cb.from_user.id)

        return await cb.message.reply_text(
            text,
            parse_mode=ParseMode.HTML
        )

    if data.startswith("ach_page_"):
        page = int(data.split("_")[-1])

        async with db.pool.acquire() as conn:
            text = await build_page(conn, cb.from_user.id, page)

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⬅️ Back", callback_data=f"ach_page_{max(page-1,0)}"),
                InlineKeyboardButton("➡️ Next", callback_data=f"ach_page_{page+1}")
            ],
            [InlineKeyboardButton("❌ Close", callback_data="ach_close")]
        ])

        await cb.message.edit_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )


OWNER_ID = 8294062042


def extract_json_array(text: str) -> str:
    start = text.find("[")
    if start == -1:
        raise ValueError("No JSON array start found")

    bracket_count = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            bracket_count += 1
        elif text[i] == "]":
            bracket_count -= 1
            if bracket_count == 0:
                return text[start:i + 1]

    raise ValueError("JSON array not closed")

def get_progress(ach, user_stats, match):
    cond = normalize_condition(ach["condition"])

    scope = cond.get("scope")
    stat = cond.get("stat")
    target = cond.get("target", 0)

    current = 0

    if scope == "career":
        current = user_stats.get(stat, 0)

    elif scope == "match":
        current = match.get(stat, 0)

    elif scope == "innings":
        current = match.get("innings_stats", {}).get(stat, 0)

    return min(current, target), target

def build_condition():
    presets = [
        # CAREER
        {"scope": "career", "stat": "runs", "target": 1000},
        {"scope": "career", "stat": "wickets", "target": 100},
        {"scope": "career", "stat": "matches", "target": 50},

        # INNINGS
        {"scope": "innings", "stat": "runs", "target": 100},
        {"scope": "innings", "stat": "wickets", "target": 5},

        # MATCH
        {"scope": "match", "stat": "runs", "target": 50},
        {"scope": "match", "stat": "wickets", "target": 3},
    ]

    chosen = random.choice(presets)

    return {
        "scope": chosen["scope"],
        "stat": chosen["stat"],
        "target": chosen["target"]
    }
async def evaluate_and_unlock_achievements(user_id: int, match=None):
    async with db.pool.acquire() as conn:

        achievements = await conn.fetch("""
            SELECT a.*
            FROM achievements a
            WHERE NOT EXISTS (
                SELECT 1 FROM user_achievements ua
                WHERE ua.user_id=$1 AND ua.achievement_id=a.id
            )
        """, user_id)

        stats = await conn.fetchrow(
            "SELECT * FROM user_stats WHERE user_id=$1",
            user_id
        ) or {}

        unlocked = []

        for ach in achievements:
            cond = normalize_condition(ach["condition"])
            scope = cond.get("scope")
            stat = cond.get("stat")
            target = cond.get("target", 0)

            current = 0

            if scope == "career":
                current = stats.get(stat, 0)

            elif scope == "match":
                current = match.get(stat, 0)

            elif scope == "innings":
                current = match.get("innings_stats", {}).get(stat, 0)

            if target > 0 and current >= target:
                await conn.execute("""
                    INSERT INTO user_achievements (user_id, achievement_id)
                    VALUES ($1,$2)
                    ON CONFLICT DO NOTHING
                """, user_id, ach["id"])

                unlocked.append(ach)

        return unlocked



def build_prompt(rarity: str, seed: int):
    return f"""
Generate EXACTLY 12 cricket achievements.

STRICT RULES:
- ALL achievements rarity = {rarity}
- Output STRICT JSON array only
- Stop immediately after ]
- Seed = {seed}

IMPORTANT CONSTRAINTS:
- DO NOT generate achievements related to:
  • catches
  • stumpings
  • run-outs
  • fielding-only actions
  • keeper-specific actions
- ONLY use actions supported by the bot:
  • batting runs
  • wickets taken
  • maidens
  • matches played
  • partnerships
  • wins / losses
  • economy / strike-based performance
  • Captaincy based records

Each item MUST be EXACTLY:
{{
  "code": "UNIQUE_CODE",
  "title": "Short title",
  "description": "One sentence requirement",
  "difficulty": 1-100
}}
"""

@Client.on_message(filters.command("gene") & filters.user(OWNER_ID))
async def generate_achievements_by_rarity(client, message):

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ Usage:\n"
            "/gene common\n"
            "/gene rare\n"
            "/gene epic\n"
            "/gene legendary"
        )

    rarity = message.command[1].lower()
    allowed = {"common", "rare", "epic", "legendary"}

    if rarity not in allowed:
        return await message.reply_text("❌ Invalid rarity.")

    status = await message.reply_text(f"⚙️ Initializing {rarity} generator...")

    async with db.pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM achievements")
        if total >= 300:
            return await status.edit_text("🛑 Global achievement limit reached (300 max).")

        if rarity == "legendary":
            legendary_count = await conn.fetchval(
                "SELECT COUNT(*) FROM achievements WHERE rarity='legendary'"
            )
            if legendary_count >= 15:
                return await status.edit_text("🛑 Legendary limit reached (15 max).")

    seed = int(time.time())

    try:
        raw = await _ai(build_prompt(rarity, seed), temp=0.3, tokens=600)
        json_text = extract_json_array(raw)
        achievements = json.loads(json_text)

        if not isinstance(achievements, list) or len(achievements) != 12:
            raise ValueError("Invalid achievement count")

    except Exception:
        print("AI RAW OUTPUT:\n", raw)
        return await status.edit_text("❌ AI failed to generate achievements.")

    inserted = 0

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            for i, ach in enumerate(achievements, start=1):

                code = f"{rarity.upper()}_{int(time.time())}_{random.randint(100,999)}"

                # 🧠 AI decides progress logic
                condition = await ai_generate_condition(
                    ach["title"],
                    ach["description"]
                )

                await conn.execute("""
                    INSERT INTO achievements
                    (code, title, description, condition, rarity, is_dynamic, difficulty)
                    VALUES ($1,$2,$3,$4::jsonb,$5,FALSE,$6)
                """,
                    code,
                    ach["title"],
                    ach["description"],
                    json.dumps(condition),
                    rarity,
                    ach["difficulty"]
                )

                inserted += 1

                await status.edit_text(
                    f"🏆 Generating {rarity.upper()} achievements\n"
                    f"✅ {i}/12 processed\n"
                    f"🎖️ {ach['title']}"
                )

    await status.edit_text(
        f"🔥 {rarity.upper()} generation complete!\n"
        f"🏆 {inserted} achievements saved\n"
        f"📦 Total ≤ 300"
    )

@Client.on_message(filters.command("delach") & filters.user(OWNER_ID))
async def delete_achievement(client, message):

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ Usage:\n"
            "/delach <achievement title>\n"
            "/delach all"
        )

    arg = " ".join(message.command[1:]).strip()

    async with db.pool.acquire() as conn:

        # 🧨 DELETE ALL (SAFE CONFIRM)
        if arg.lower() == "all":
            await conn.execute("DELETE FROM user_achievements")
            await conn.execute("DELETE FROM achievements")

            return await message.reply_text(
                "🧨 <b>ALL achievements deleted.</b>\n"
                "Database reset complete.",
                parse_mode=ParseMode.HTML
            )

        # 🗑️ DELETE BY TITLE
        row = await conn.fetchrow("""
            SELECT id, title
            FROM achievements
            WHERE LOWER(title) = LOWER($1)
            LIMIT 1
        """, arg)

        if not row:
            return await message.reply_text(
                "❌ Achievement not found.\n"
                "Tip: Title must match exactly."
            )

        await conn.execute(
            "DELETE FROM achievements WHERE id=$1",
            row["id"]
        )

    await message.reply_text(
        f"🗑️ Achievement deleted:\n<b>{row['title']}</b>",
        parse_mode=ParseMode.HTML
    )
