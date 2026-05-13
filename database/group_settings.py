from database.connection import db

DEFAULTS = {
    "super_over":         False,
    "ai_summary":         True,
    "achievement_alerts": True,
    "auto_play_again":    True,
    "spam_free":          False,
    "edge_rule":          False,
    "disabled_numbers":   [],
    "ball_timeout":       60,
    "team_names":         False,
}

_cache: dict = {}


async def get_group_settings(chat_id: int) -> dict:
    if chat_id in _cache:
        return _cache[chat_id]
    await db.ensure_pool()
    doc = await db.db["group_settings"].find_one({"chat_id": chat_id})
    if doc:
        settings = {**DEFAULTS, **{k: v for k, v in doc.items() if k not in ("_id", "chat_id")}}
    else:
        settings = dict(DEFAULTS)
    _cache[chat_id] = settings
    return settings


async def get_setting(chat_id: int, key: str):
    s = await get_group_settings(chat_id)
    return s.get(key, DEFAULTS.get(key))


async def set_group_setting(chat_id: int, key: str, value) -> None:
    if chat_id not in _cache:
        await get_group_settings(chat_id)
    _cache[chat_id][key] = value
    await db.ensure_pool()
    await db.db["group_settings"].update_one(
        {"chat_id": chat_id},
        {"$set": {key: value}},
        upsert=True,
    )


def invalidate_cache(chat_id: int) -> None:
    _cache.pop(chat_id, None)
