import io
import time
import traceback
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from pyrogram import Client, filters
from pyrogram.enums import ParseMode

from database.users import total_users
from database.groups import total_groups
from database.connection import db
from config import Config

FONT_PATH = "Assets/fonts.ttf"
NAME_FONT = "Assets/namefont.ttf"
BOT_START_TIME = time.time()

# ── Palette ───────────────────────────────────────────────────────────────────
BG_TOP  = (8, 6, 18)
BG_BOT  = (18, 10, 32)
ACCENT  = (140, 80, 255)
ACCENT2 = (80, 180, 255)
WHITE   = (245, 245, 250)
MUTED   = (160, 155, 180)
CARD_BG = (26, 20, 46)
DIVIDER = (55, 40, 90)

W, H = 1280, 680


def get_uptime() -> str:
    secs = int(time.time() - BOT_START_TIME)
    h, rem = divmod(secs, 3600)
    m = rem // 60
    return f"{h}h {m}m"


def _gradient_bg(draw: ImageDraw.ImageDraw):
    for y in range(H):
        t = y / H
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


def _glow_circle(img: Image.Image, cx: int, cy: int, r: int, color: tuple):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(4, 0, -1):
        alpha = 25 * i
        d.ellipse(
            [cx - r - i * 6, cy - r - i * 6, cx + r + i * 6, cy + r + i * 6],
            fill=color + (alpha,),
        )
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (255,))
    img.alpha_composite(layer)


def _rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)


def _load_font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def build_stats_image(
    users, groups, games_today, games_total, active_games, uptime,
    bot_label: str = "NEXORA CRICKET",
    bot_tag: str = "@NexoraSystems",
    is_clone: bool = False,
) -> io.BytesIO:
    img  = Image.new("RGBA", (W, H), BG_TOP)
    draw = ImageDraw.Draw(img)
    _gradient_bg(draw)

    # ── fonts ─────────────────────────────────────────────────────────────────
    f_title  = _load_font(NAME_FONT, 54)
    f_big    = _load_font(NAME_FONT, 96)
    f_label  = _load_font(FONT_PATH, 28)
    f_sub    = _load_font(FONT_PATH, 22)
    f_card_v = _load_font(NAME_FONT, 46)
    f_card_l = _load_font(FONT_PATH, 22)

    # ── top accent bar ────────────────────────────────────────────────────────
    accent_col = (80, 160, 255) if is_clone else ACCENT
    draw.rectangle([(0, 0), (W, 5)], fill=accent_col)

    # ── clone badge ───────────────────────────────────────────────────────────
    if is_clone:
        draw.rounded_rectangle([W - 190, 12, W - 20, 46], radius=14, fill=(20, 50, 120))
        draw.text((W - 105, 29), "🧬 CLONE BOT", font=f_sub, fill=(130, 200, 255), anchor="mm")

    # ── title ─────────────────────────────────────────────────────────────────
    draw.text((W // 2, 44), bot_label.upper(), font=f_title, fill=WHITE, anchor="mm")
    draw.text((W // 2, 80), "Live Statistics", font=f_sub, fill=MUTED, anchor="mm")

    # ── thin divider ──────────────────────────────────────────────────────────
    draw.rectangle([(80, 100), (W - 80, 102)], fill=DIVIDER)

    # ── center hero: total players ────────────────────────────────────────────
    img_rgba = img.convert("RGBA")
    cx, cy, cr = W // 2, 260, 110
    glow = Image.new("RGBA", img_rgba.size, (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    for i in range(5, 0, -1):
        gd.ellipse(
            [cx - cr - i * 14, cy - cr - i * 14, cx + cr + i * 14, cy + cr + i * 14],
            fill=accent_col + (18 * i,),
        )
    img_rgba = Image.alpha_composite(img_rgba, glow)
    draw2 = ImageDraw.Draw(img_rgba)
    draw2.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=CARD_BG, outline=accent_col, width=3)
    draw2.text((cx, cy - 20), f"{users:,}", font=f_big, fill=WHITE, anchor="mm")
    draw2.text((cx, cy + 54), "PLAYERS", font=f_label, fill=accent_col, anchor="mm")

    img  = img_rgba.convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── stat cards row ────────────────────────────────────────────────────────
    cards = [
        ("👥", f"{groups:,}", "Groups"),
        ("🎮", f"{games_today:,}", "Games Today"),
        ("⚡", f"{active_games}", "Live Now"),
        ("📊", f"{games_total:,}", "Total Games"),
        ("⏱",  uptime,            "Uptime"),
    ]

    card_w, card_h = 194, 110
    gap            = 24
    total_card_w   = len(cards) * card_w + (len(cards) - 1) * gap
    start_x        = (W - total_card_w) // 2
    card_y         = 416

    for idx, (icon, val, label) in enumerate(cards):
        cx_ = start_x + idx * (card_w + gap)
        _rounded_rect(draw, [cx_, card_y, cx_ + card_w, card_y + card_h], 16, CARD_BG)
        draw.rounded_rectangle(
            [cx_, card_y, cx_ + card_w, card_y + card_h],
            radius=16, outline=DIVIDER, width=1,
        )
        draw.text((cx_ + card_w // 2, card_y + 22), icon,  font=f_card_l, fill=WHITE,         anchor="mm")
        draw.text((cx_ + card_w // 2, card_y + 56), val,   font=f_card_v, fill=WHITE,         anchor="mm")
        draw.text((cx_ + card_w // 2, card_y + 88), label, font=f_card_l, fill=MUTED,         anchor="mm")

    # ── bottom accent ─────────────────────────────────────────────────────────
    draw.rectangle([(0, H - 5), (W, H)], fill=ACCENT2)

    # ── footer ────────────────────────────────────────────────────────────────
    draw.text(
        (W // 2, H - 22),
        f"🕐 {datetime.now(timezone.utc).strftime('%d %b %Y  %H:%M')} UTC  •  {bot_tag}",
        font=f_sub, fill=MUTED, anchor="mm",
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@Client.on_message(filters.command(["stats", "botstats"]))
async def stats_cmd(client, message):
    loading = None
    try:
        loading = await message.reply_text("📊 Pulling live stats…")
    except Exception:
        pass

    try:
        users = groups = games_today = games_total = active_games = 0

        try:
            users = await total_users()
        except Exception:
            pass
        try:
            groups = await total_groups()
        except Exception:
            pass
        try:
            today_start  = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            games_today  = await db.db["games"].count_documents({"created_at": {"$gte": today_start}})
            games_total  = await db.db["games"].count_documents({})
            active_games = await db.db["games"].count_documents({"status": "active"})
        except Exception:
            pass

        uptime = get_uptime()

        # ── clone-aware labelling ─────────────────────────────────────────────
        is_clone = Config.IS_CLONE
        if is_clone:
            try:
                me        = await client.get_me()
                bot_label = me.first_name or "Clone Bot"
                bot_tag   = f"@{me.username}" if me.username else "@CloneBot"
            except Exception:
                bot_label = "Clone Bot"
                bot_tag   = "@CloneBot"
        else:
            bot_label = "NEXORA CRICKET"
            bot_tag   = "@NexoraSystems"

        img = build_stats_image(
            users=users,
            groups=groups,
            games_today=games_today,
            games_total=games_total,
            active_games=active_games,
            uptime=uptime,
            bot_label=bot_label,
            bot_tag=bot_tag,
            is_clone=is_clone,
        )

        if loading:
            try:
                await loading.delete()
            except Exception:
                pass

        await client.send_photo(chat_id=message.chat.id, photo=img)

    except Exception:
        traceback.print_exc()
        try:
            msg = "⚠️ Stats are temporarily unavailable.\nTry again in a bit."
            if loading:
                await loading.edit_text(msg)
            else:
                await message.reply_text(msg)
        except Exception:
            pass
