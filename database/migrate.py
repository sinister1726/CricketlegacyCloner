from database.connection import db


async def migrate():
    database = db.db

    await database["users"].create_index("user_id", unique=True)
    await database["mods"].create_index("user_id", unique=True)
    await database["user_bans"].create_index("user_id", unique=True)
    await database["group_bans"].create_index("chat_id", unique=True)
    await database["games"].create_index("game_id", unique=True)
    await database["games"].create_index([("chat_id", 1), ("status", 1)])
    await database["game_players"].create_index([("game_id", 1), ("user_id", 1)])
    await database["game_players"].create_index("user_id")
    await database["team_shifts"].create_index([("game_id", 1), ("user_id", 1)], unique=True)
    await database["user_stats"].create_index("user_id", unique=True)
    await database["achievements"].create_index("code", unique=True)
    await database["user_achievements"].create_index([("user_id", 1), ("achievement_id", 1)], unique=True)
    await database["user_achievements"].create_index("user_id")
    await database["duel_stats"].create_index("user_id", unique=True)
    await database["duel_stats"].create_index([("wins", -1)])
    await database["groups"].create_index("chat_id", unique=True)
    await database["restricted_users"].create_index("user_id", unique=True)
    await database["gbans"].create_index("user_id", unique=True)
    await database["achievement_meta"].create_index("key", unique=True)

    await database["achievement_meta"].update_one(
        {"key": "generation_count"},
        {"$setOnInsert": {"key": "generation_count", "value": 0}},
        upsert=True
    )

    await database["group_settings"].create_index("chat_id", unique=True)
    await database["premium_groups"].create_index("chat_id", unique=True)
    await database["user_premium"].create_index("user_id", unique=True)
    await database["user_clones"].create_index("user_id", unique=True)
    await database["clone_settings"].create_index("owner_id", unique=True)
    await database["venue_stats"].create_index([("user_id", 1), ("chat_id", 1)], unique=True)
    await database["venue_stats"].create_index([("chat_id", 1), ("runs", -1)])
    await database["venue_stats"].create_index([("user_id", 1), ("runs", -1)])
    await database["venue_stats"].create_index("runs")
    await database["venue_stats"].create_index("wickets")

    print("✅ MongoDB indexes created. Database migration complete.")
