"""
Custom game media storage.
Stores owner-uploaded file_ids in MongoDB so they persist across restarts
and override the hardcoded defaults in Assets/files.py.

Collection: game_media (global — not per-clone prefix)
Document:   { _id: "run_6", ids: ["file_id_1", "file_id_2"] }
"""
from database.connection import db

_COL = "game_media"


def _doc_id(category: str, key) -> str:
    return f"{category}_{key}"


async def get_media_ids(category: str, key) -> list[str]:
    """Return stored file_ids for this category+key, or [] if none."""
    doc = await db.real_db[_COL].find_one({"_id": _doc_id(category, key)})
    return doc["ids"] if doc else []


async def add_media_id(category: str, key, file_id: str) -> list[str]:
    """Append a file_id.  Returns the updated list."""
    did = _doc_id(category, key)
    await db.real_db[_COL].update_one(
        {"_id": did},
        {"$addToSet": {"ids": file_id}},
        upsert=True,
    )
    doc = await db.real_db[_COL].find_one({"_id": did})
    return doc["ids"] if doc else [file_id]


async def remove_media_id(category: str, key, file_id: str) -> list[str]:
    """Remove a specific file_id.  Returns updated list."""
    did = _doc_id(category, key)
    await db.real_db[_COL].update_one({"_id": did}, {"$pull": {"ids": file_id}})
    doc = await db.real_db[_COL].find_one({"_id": did})
    return doc["ids"] if doc else []


async def clear_media_key(category: str, key) -> None:
    """Delete all stored file_ids for this key."""
    await db.real_db[_COL].delete_one({"_id": _doc_id(category, key)})


async def list_all_media() -> list[dict]:
    """Return all stored media documents."""
    return await db.real_db[_COL].find().to_list(length=None)
