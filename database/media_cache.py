"""
Per-bot media file_id cache.
Stored globally (not per-clone-prefix) because the key already includes bot_id.
"""
from database.connection import db


async def get_cached_file_id(bot_id: int, media_key: str) -> str | None:
    doc = await db.real_db["media_file_cache"].find_one(
        {"bot_id": bot_id, "key": media_key}
    )
    return doc["file_id"] if doc else None


async def set_cached_file_id(bot_id: int, media_key: str, file_id: str) -> None:
    await db.real_db["media_file_cache"].update_one(
        {"bot_id": bot_id, "key": media_key},
        {"$set": {"file_id": file_id}},
        upsert=True,
    )


async def clear_bot_media_cache(bot_id: int) -> int:
    """Wipe all cached file_ids for a bot (e.g. when token is rotated)."""
    result = await db.real_db["media_file_cache"].delete_many({"bot_id": bot_id})
    return result.deleted_count


async def clear_media_key_for_all(key_prefix: str) -> int:
    """
    Wipe cached file_ids matching a key prefix across ALL clone bots.
    Used after /addfile so clones pick up the new file on next use.
    Matches any key starting with key_prefix (e.g. "run_6" wipes run_6_0, run_6_1…)
    """
    import re
    pattern = re.compile(f"^{re.escape(key_prefix)}")
    docs    = await db.real_db["media_file_cache"].find({}, {"key": 1}).to_list(length=None)
    keys_to_del = [d["key"] for d in docs if pattern.match(d.get("key", ""))]
    if not keys_to_del:
        return 0
    result = await db.real_db["media_file_cache"].delete_many({"key": {"$in": keys_to_del}})
    return result.deleted_count
