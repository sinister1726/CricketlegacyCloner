from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os

ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Assets")
FONT_PATH = os.path.join(ASSETS, "fonts.ttf")
NAME_FONT_PATH = os.path.join(ASSETS, "namefont.ttf")


def _load_font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            return ImageFont.load_default()


def generate_panel_image(bot_username: str = "", owner_name: str = "") -> BytesIO:
    W, H = 1280, 520

    img = Image.new("RGB", (W, H), (8, 12, 28))
    draw = ImageDraw.Draw(img)

    # ── Background gradient ───────────────────────────────────────────────────
    for y in range(H):
        t = y / H
        r = int(8 + t * 10)
        g = int(12 + t * 18)
        b = int(28 + t * 48)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # ── Decorative blobs ──────────────────────────────────────────────────────
    for cx, cy, r, col in [
        (-60, -60, 260, (18, 42, 90)),
        (W + 40, -80, 300, (15, 38, 85)),
        (W - 100, H + 60, 240, (12, 30, 70)),
        (480, H - 20, 180, (14, 34, 78)),
    ]:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    # ── Cricket ball ring (right side) ────────────────────────────────────────
    bx, by, br = W - 130, H // 2, 130
    draw.ellipse([bx - br, by - br, bx + br, by + br], outline=(50, 110, 220), width=3)
    draw.ellipse([bx - br + 30, by - br + 30, bx + br - 30, by + br - 30], outline=(40, 90, 180), width=2)
    draw.line([bx - br, by, bx + br, by], fill=(50, 110, 220), width=2)
    draw.arc([bx - 70, by - 80, bx + 70, by], 0, 180, fill=(80, 150, 255), width=2)

    # ── Accent borders ────────────────────────────────────────────────────────
    draw.rectangle([0, 0, W, 5], fill=(56, 139, 253))
    draw.rectangle([0, H - 5, W, H], fill=(56, 139, 253))
    draw.rectangle([0, 0, 6, H], fill=(56, 139, 253))

    # ── Fonts ─────────────────────────────────────────────────────────────────
    f_xl   = _load_font(NAME_FONT_PATH, 80)
    f_lg   = _load_font(FONT_PATH, 38)
    f_md   = _load_font(FONT_PATH, 28)
    f_sm   = _load_font(FONT_PATH, 22)

    # ── Badge chip ────────────────────────────────────────────────────────────
    draw.rounded_rectangle([40, 48, 230, 88], radius=22, fill=(25, 65, 155))
    draw.text((60, 58), "CLONE  BOT", fill=(140, 200, 255), font=f_sm)

    # ── Main title ────────────────────────────────────────────────────────────
    draw.text((40, 105), "BOT PANEL", fill=(240, 248, 255), font=f_xl)

    # ── Bot username ──────────────────────────────────────────────────────────
    if bot_username:
        draw.text((46, 205), bot_username, fill=(90, 160, 255), font=f_lg)

    # ── Divider ───────────────────────────────────────────────────────────────
    draw.rectangle([40, 255, 700, 258], fill=(40, 90, 190))

    # ── Settings tiles ────────────────────────────────────────────────────────
    tiles = [
        ("🖼  Start Image",    (40,  272)),
        ("📝  Start Message",  (270, 272)),
        ("🔗  Support Link",   (500, 272)),
        ("🎮  PlayZone Link",  (40,  330)),
        ("📢  Log Channel",    (270, 330)),
    ]
    for label, (tx, ty) in tiles:
        draw.rounded_rectangle([tx, ty, tx + 210, ty + 42], radius=10, fill=(18, 45, 105))
        draw.text((tx + 12, ty + 10), label, fill=(180, 220, 255), font=f_sm)

    # ── Bottom brand ──────────────────────────────────────────────────────────
    draw.text((40, H - 58), "Nexora Cricket", fill=(50, 110, 200), font=f_md)
    if owner_name:
        txt = f"Owner: {owner_name}"
        draw.text((W - 350, H - 58), txt, fill=(70, 130, 210), font=f_sm)

    # ── Glow dots row ────────────────────────────────────────────────────────
    for i in range(6):
        cx = 40 + i * 28
        cy = H - 80
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(56, 139, 253))

    buf = BytesIO()
    img.save(buf, format="PNG", quality=95)
    buf.seek(0)
    buf.name = "panel_banner.png"
    return buf
