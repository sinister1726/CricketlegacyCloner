"""
Unified media resolver — returns a working Telegram file_id for any bot.

Main bot  → returns a source file_id directly (was uploaded by the main bot token).
Clone bot → checks per-bot MongoDB cache first; if missing, uploads the local
            disk copy via the clone bot's token (sent silently to the clone
            owner's DM then deleted), caches the new file_id, and returns it.
"""
import asyncio
import random
from pathlib import Path

from config import Config
from database.media_cache import get_cached_file_id, set_cached_file_id
from utils.media_downloader import MEDIA_DIR


# ── internal helpers ──────────────────────────────────────────────────────────

def _source_list(category: str, key) -> tuple[list[str], str]:
    """Return (valid_source_ids, disk_key_prefix) for a given category+key."""
    from Assets.files import RUN_VIDEOS, ACHIEVE_VIDEOS

    safe_k = str(key).replace(" ", "_").replace("/", "-")
    if category == "run":
        ids    = RUN_VIDEOS.get(str(key), [])
        prefix = f"run_{safe_k}"
    else:
        ids    = ACHIEVE_VIDEOS.get(key, [])
        prefix = f"achieve_{safe_k}"

    valid = [v for v in ids if v and not v.startswith("FILE_ID")]
    return valid, prefix


async def _upload_from_disk(client, disk_key: str) -> str | None:
    """
    Upload the local file to the clone owner's DM (silent, no caption),
    read the returned file_id, then delete the message.
    """
    path = MEDIA_DIR / f"{disk_key}.bin"
    if not path.exists() or path.stat().st_size == 0:
        return None

    owner = Config.CLONE_OWNER_ID
    msg   = None
    fid   = None

    # Try as video first, then as animation (GIF)
    for send_fn, attr in (("send_video", "video"), ("send_animation", "animation")):
        try:
            msg = await getattr(client, send_fn)(
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
            continue

    # Clean up the silent message from the owner's DM
    if msg:
        try:
            await msg.delete()
        except Exception:
            pass

    return fid


# ── public API ────────────────────────────────────────────────────────────────

async def get_video_file_id(client, category: str, key) -> str | None:
    """
    Resolve a working file_id for this bot client.

    Args:
        client:   Pyrogram Client instance.
        category: "run"     → key is "0"–"6", "Out", "Batting", "Bowling", "Opening"
                  "achieve" → key is int or str  (50, "HAT_TRICK", "Duck", …)
    Returns:
        A Telegram file_id string, or None if unavailable (caller should fall
        back to a plain text/photo message).
    """
    valid_ids, prefix = _source_list(category, key)
    if not valid_ids:
        return None

    # ── Main bot: source file_ids already work ────────────────────────────────
    if not Config.IS_CLONE:
        return random.choice(valid_ids)

    # ── Clone bot: check per-bot MongoDB cache ────────────────────────────────
    me     = await client.get_me()
    bot_id = me.id

    # Try every slot; pick a random one to vary animations
    indices = list(range(len(valid_ids)))
    random.shuffle(indices)

    for i in indices:
        cache_key = f"{prefix}_{i}"
        cached    = await get_cached_file_id(bot_id, cache_key)
        if cached:
            return cached

        # Not cached → upload from local disk
        disk_key = f"{prefix}_{i}"
        fid      = await _upload_from_disk(client, disk_key)
        if fid:
            await set_cached_file_id(bot_id, cache_key, fid)
            return fid

    # Local disk not ready yet (main bot hasn't finished startup download)
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
    Convenience wrapper: resolves file_id, sends video/animation, falls back to
    text (or photo) if media is unavailable.
    """
    from pyrogram.enums import ParseMode

    fid = await get_video_file_id(client, category, key)

    if fid:
        for send_fn, attr in (("send_video", "video"), ("send_animation", "animation")):
            try:
                return await getattr(client, send_fn)(
                    chat_id=chat_id,
                    **{attr: fid},
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                err = str(e).upper()
                # If it's a file_id/content-type error, wipe the cache and continue
                if any(x in err for x in ("FILE_ID", "MEDIA_EMPTY", "CONTENT_TYPE", "ANIMATION")):
                    continue
                break

    # Fallback
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
