from database.connection import db
from datetime import datetime, timedelta

_prem_cache: dict = {}


async def grant_clone_premium(user_id: int, granted_by: int, days: int = 28) -> bool:
    await db.ensure_pool()
    expires_at = datetime.utcnow() + timedelta(days=days)
    await db.db["user_premium"].update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "active": True,
            "granted_by": granted_by,
            "granted_at": datetime.utcnow(),
            "expires_at": expires_at,
        }},
        upsert=True,
    )
    _prem_cache[user_id] = {"active": True, "expires_at": expires_at}
    return True


async def revoke_clone_premium(user_id: int) -> bool:
    await db.ensure_pool()
    clone = await get_clone_process(user_id)
    if clone and clone.get("pid"):
        try:
            import os, signal
            os.kill(clone["pid"], signal.SIGTERM)
        except Exception:
            pass
    await db.db["user_premium"].update_one(
        {"user_id": user_id}, {"$set": {"active": False}}
    )
    await db.db["user_clones"].update_one(
        {"user_id": user_id}, {"$set": {"running": False, "pid": None}}
    )
    _prem_cache.pop(user_id, None)
    return True


async def is_clone_premium(user_id: int) -> bool:
    cached = _prem_cache.get(user_id)
    if cached:
        if not cached.get("active"):
            return False
        exp = cached.get("expires_at")
        if exp and datetime.utcnow() > exp:
            _prem_cache[user_id] = {"active": False}
            return False
        return True
    await db.ensure_pool()
    doc = await db.db["user_premium"].find_one({"user_id": user_id, "active": True})
    if not doc:
        _prem_cache[user_id] = {"active": False}
        return False
    exp = doc.get("expires_at")
    if exp and datetime.utcnow() > exp:
        _prem_cache[user_id] = {"active": False}
        await db.db["user_premium"].update_one({"user_id": user_id}, {"$set": {"active": False}})
        return False
    _prem_cache[user_id] = {"active": True, "expires_at": exp}
    return True


async def get_clone_premium(user_id: int):
    await db.ensure_pool()
    return await db.db["user_premium"].find_one({"user_id": user_id})


async def set_clone_process(user_id: int, token: str, pid: int, bot_username: str) -> None:
    await db.ensure_pool()
    await db.db["user_clones"].update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "token": token,
            "pid": pid,
            "bot_username": bot_username,
            "running": True,
            "started_at": datetime.utcnow(),
        }},
        upsert=True,
    )


async def get_clone_process(user_id: int):
    await db.ensure_pool()
    return await db.db["user_clones"].find_one({"user_id": user_id})


async def clear_clone_process(user_id: int) -> None:
    await db.ensure_pool()
    await db.db["user_clones"].update_one(
        {"user_id": user_id},
        {"$set": {"running": False, "pid": None}},
    )


async def get_all_active_clones():
    await db.ensure_pool()
    cursor = db.db["user_clones"].find({"running": True})
    return await cursor.to_list(length=None)


async def get_clone_setting(owner_id: int, key: str):
    await db.ensure_pool()
    doc = await db.db["clone_settings"].find_one({"owner_id": owner_id})
    if not doc:
        return None
    return doc.get(key)


async def set_clone_setting(owner_id: int, key: str, value) -> None:
    await db.ensure_pool()
    await db.db["clone_settings"].update_one(
        {"owner_id": owner_id},
        {"$set": {key: value, "owner_id": owner_id}},
        upsert=True,
    )


async def get_all_clone_settings(owner_id: int) -> dict:
    await db.ensure_pool()
    doc = await db.db["clone_settings"].find_one({"owner_id": owner_id})
    return doc or {}


async def check_and_expire_clones(bot=None):
    await db.ensure_pool()
    now = datetime.utcnow()
    cursor = db.db["user_premium"].find({"active": True, "expires_at": {"$lt": now}})
    async for doc in cursor:
        uid = doc["user_id"]
        await db.db["user_premium"].update_one({"_id": doc["_id"]}, {"$set": {"active": False}})
        _prem_cache.pop(uid, None)
        clone = await db.db["user_clones"].find_one({"user_id": uid, "running": True})
        if clone and clone.get("pid"):
            try:
                import os, signal
                os.kill(clone["pid"], signal.SIGTERM)
            except Exception:
                pass
        await db.db["user_clones"].update_one(
            {"user_id": uid}, {"$set": {"running": False, "pid": None}}
        )
        if bot:
            try:
                await bot.send_message(
                    uid,
                    "⏰ <b>Your clone bot has expired!</b>\n\n"
                    "Your 28-day clone premium has ended and your bot has been stopped.\n\n"
                    "💬 Contact <b>@Spideyyye</b> to renew — ₹200/month.",
                    parse_mode="html",
                )
            except Exception:
                pass
        print(f"⏰ Clone premium expired for user {uid}")
