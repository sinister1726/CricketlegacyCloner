"""
Unified media resolver — returns a working Telegram file_id for any bot.

Source priority (highest → lowest):
  1. MongoDB game_media collection  (owner-uploaded fresh file_ids)
  2. Assets/files.py defaults       (original hardcoded file_ids)

Main bot  → returns a source file_id directly.
Clone bot → checks per-bot MongoDB cache; uploads from local disk if missing.
"""
import random
from pathlib import Path

from config import Config
from database.media_cache import get_cached_file_id, set_cached_file_id
from utils.media_downloader import MEDIA_DIR


# ── source resolution ─────────────────────────────────────────────────────────

def _static_ids(category: str, key) -> list[str]:
    """Return valid file_ids from Assets/files.py for this category+key."""
    from Assets.files import RUN_VIDEOS, ACHIEVE_VIDEOS
    if category == "run":
        ids = RUN_VIDEOS.get(str(key), [])
    else:
        ids = ACHIEVE_VIDEOS.get(key, [])
    return [v for v in ids if v and not v.startswith("FILE_ID")]


async def _all_source_ids(category: str, key) -> tuple[list[str], str]:
    """
    Return (merged_valid_ids, disk_key_prefix).
    DB ids come first so freshly uploaded files take priority.
    """
    from database.game_media import get_media_ids

    safe_k = str(key).replace(" ", "_").replace("/", "-")
    prefix = f"{category}_{safe_k}"

    db_ids     = await get_media_ids(category, key)
    static_ids = _static_ids(category, key)

    # DB ids first, then static; deduplicate while preserving order
    seen  = set()
    final = []
    for fid in db_ids + static_ids:
        if fid not in seen:
            seen.add(fid)
            final.append(fid)

    return final, prefix


# ── clone bot: upload from disk ───────────────────────────────────────────────

async def _upload_from_disk(client, disk_key: str) -> str | None:
    """
    Upload /tmp/nexora_media/<disk_key>.bin to clone owner's DM (silent),
    read the returned file_id, cache it, then delete the message.
    """
    path = MEDIA_DIR / f"{disk_key}.bin"
    if not path.exists() or path.stat().st_size == 0:
        return None

    owner = Config.CLONE_OWNER_ID
    msg   = None
    fid   = None

    for method, attr in (("send_video", "video"), ("send_animation", "animation"), ("send_document", "document")):
        try:
            msg = await getattr(client, method)(
                chat_id=owner,
                **{attr: str(path)},
                disable_notification=True,
            )
            media = getattr(msg, attr, None)
            if media:
                fid = media.file_id
                break
        except Exception:
            msg = None

    if msg:
        try:
            await msg.delete()
        except Exception:
            pass

    return fid


# ── public API ────────────────────────────────────────────────────────────────

async def get_video_file_id(client, category: str, key) -> str | None:
    """
    Resolve a working Telegram file_id for this bot client.

    category: "run"     → key in "0"-"6", "Out", "Batting", "Bowling", "Opening"
              "achieve" → key is int or str  (50, "HAT_TRICK", "Duck", …)
    """
    valid_ids, prefix = await _all_source_ids(category, key)
    if not valid_ids:
        return None

    # ── Main bot: source file_ids work directly ───────────────────────────────
    if not Config.IS_CLONE:
        return random.choice(valid_ids)

    # ── Clone bot: check per-bot MongoDB cache ────────────────────────────────
    me     = await client.get_me()
    bot_id = me.id

    indices = list(range(len(valid_ids)))
    random.shuffle(indices)

    for i in indices:
        cache_key = f"{prefix}_{i}"

        cached = await get_cached_file_id(bot_id, cache_key)
        if cached:
            return cached

        fid = await _upload_from_disk(client, f"{prefix}_{i}")
        if fid:
            await set_cached_file_id(bot_id, cache_key, fid)
            return fid

    return None


async def send_video_or_fallback(
    client,
    chat_id: int,
    category: str,
    key,
    caption: str,
    reply_markup=None,
    fallback_photo: str | None = None,
):
    """
    Resolve file_id, send video/animation, fall back to photo or plain text.
    """
    from pyrogram.enums import ParseMode

    fid = await get_video_file_id(client, category, key)

    if fid:
        for method, attr in (("send_video", "video"), ("send_animation", "animation")):
            try:
                return await getattr(client, method)(
                    chat_id=chat_id,
                    **{attr: fid},
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                err = str(e).upper()
                if any(x in err for x in ("FILE_ID", "MEDIA_EMPTY", "CONTENT_TYPE", "ANIMATION", "MEDIA_INVALID")):
                    continue
                break

    if fallback_photo:
        try:
            return await client.send_photo(
                chat_id=chat_id,
                photo=fallback_photo,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    return await client.send_message(
        chat_id=chat_id,
        text=caption,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )
