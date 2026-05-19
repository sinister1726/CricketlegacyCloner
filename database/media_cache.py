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
