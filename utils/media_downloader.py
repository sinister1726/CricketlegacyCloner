"""
Media source downloader.

Tries to save each source video/GIF to /tmp/nexora_media/<disk_key>.bin
so that clone bots (running on the same machine) can upload them with
their own token and cache their own file_ids in MongoDB.

Strategy: send the file_id to an active group or the owner DM to get
a fresh message with a valid file reference, then download from that.
"""
import asyncio
from pathlib import Path

from Assets.files import RUN_VIDEOS, ACHIEVE_VIDEOS

MEDIA_DIR = Path("/tmp/nexora_media")


def _iter_all_sources():
    """Yields (disk_key, file_id) for every non-empty source entry."""
    for k, ids in RUN_VIDEOS.items():
        safe_k = str(k).replace(" ", "_")
        for i, fid in enumerate(ids):
            if fid and not fid.startswith("FILE_ID"):
                yield f"run_{safe_k}_{i}", fid

    for k, ids in ACHIEVE_VIDEOS.items():
        safe_k = str(k).replace(" ", "_").replace("/", "-")
        for i, fid in enumerate(ids):
            if fid and not fid.startswith("FILE_ID"):
                yield f"achieve_{safe_k}_{i}", fid


async def _find_dump_target(client, owner_id: int) -> int | None:
    """
    Return a chat_id the bot can definitely send to.
    Priority: owner DM → any known group in DB.
    """
    # Try owner DM first (works if they've started the bot)
    try:
        test = await client.send_message(owner_id, "🔧 Media setup running…", disable_notification=True)
        await test.delete()
        return owner_id
    except Exception:
        pass

    # Fall back to any group in the DB
    try:
        from database.groups import get_all_groups
        groups = await get_all_groups()
        for g in (groups or []):
            gid = g.get("chat_id") or g.get("_id")
            if not gid:
                continue
            try:
                test = await client.send_message(int(gid), "🔧", disable_notification=True)
                await test.delete()
                return int(gid)
            except Exception:
                continue
    except Exception:
        pass

    return None


async def download_single(client, disk_key: str, file_id: str, dump_target: int) -> bool:
    """
    Send file_id to dump_target, download the returned message, save to disk.
    Returns True on success.
    """
    dest = MEDIA_DIR / f"{disk_key}.bin"
    if dest.exists() and dest.stat().st_size > 0:
        return True

    msg      = None
    sent_ok  = False

    for method, kwarg in (("send_video", "video"), ("send_animation", "animation"), ("send_document", "document")):
        try:
            msg = await getattr(client, method)(
                chat_id=dump_target,
                **{kwarg: file_id},
                disable_notification=True,
            )
            sent_ok = True
            break
        except Exception:
            msg = None

    if not sent_ok or msg is None:
        return False

    try:
        await client.download_media(msg, file_name=str(dest))
        return True
    except Exception:
        return False
    finally:
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass


async def download_all_source_media(client) -> int:
    """
    Called at main-bot startup (background task).
    Returns the number of newly saved files.
    """
    from config import Config

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    owner_id     = next(iter(Config.OWNER_IDS))
    dump_target  = await _find_dump_target(client, owner_id)

    if dump_target is None:
        print(
            "[MediaDownloader] ⚠️  No suitable dump target found. "
            "Run /mediasetup in bot DM to cache media for clone bots."
        )
        return 0

    downloaded = 0
    failed     = []

    for disk_key, file_id in _iter_all_sources():
        dest = MEDIA_DIR / f"{disk_key}.bin"
        if dest.exists() and dest.stat().st_size > 0:
            continue

        ok = await download_single(client, disk_key, file_id, dump_target)
        if ok:
            downloaded += 1
        else:
            failed.append(disk_key)

        await asyncio.sleep(0.2)

    if failed:
        print(
            f"[MediaDownloader] ⚠️  {len(failed)} file(s) unavailable "
            f"(may need re-uploading). Run /mediasetup as owner to fix."
        )
    return downloaded
