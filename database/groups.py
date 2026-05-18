from datetime import datetime
from database.connection import db


async def add_group(chat_id: int, title: str) -> bool:
    col = db.db["groups"]
    existing = await col.find_one({"chat_id": chat_id})
    if existing:
        return False
    await col.insert_one({"chat_id": chat_id, "title": title, "created_at": datetime.utcnow()})
    return True


async def total_groups() -> int:
    return await db.db["groups"].count_documents({})


async def get_all_groups() -> list:
    cursor = db.db["groups"].find({}, {"chat_id": 1, "title": 1})
    return await cursor.to_list(length=None)
