from database.connection import db

async def add_user(user_id: int, name: str) -> bool:
    async with db.pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT user_id FROM users WHERE user_id=$1",
            user_id
        )

        if exists:
            return False

        await conn.execute(
            "INSERT INTO users (user_id, name) VALUES ($1, $2)",
            user_id, name
        )
        return True


async def total_users() -> int:
    async with db.pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")

from database.connection import db

# ───── USER BANS ─────
async def ban_user(user_id, first_name, reason, by):
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_bans (user_id, first_name, reason, banned_by)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (user_id)
            DO UPDATE SET
                reason=$3,
                banned_by=$4,
                banned_at=NOW()
            """,
            user_id, first_name, reason, by
        )

async def unban_user(user_id):
    async with db.pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM user_bans WHERE user_id=$1",
            user_id
        )

async def get_user_ban(user_id):
    async with db.pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM user_bans WHERE user_id=$1",
            user_id
        )

async def list_user_bans():
    async with db.pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM user_bans")


# ───── GROUP BANS ─────
async def ban_group(chat_id, title, reason, by):
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO group_bans (chat_id, title, reason, banned_by)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (chat_id)
            DO UPDATE SET
                reason=$3,
                banned_by=$4,
                banned_at=NOW()
            """,
            chat_id, title, reason, by
        )

async def unban_group(chat_id):
    async with db.pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM group_bans WHERE chat_id=$1",
            chat_id
        )

async def get_group_ban(chat_id):
    async with db.pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM group_bans WHERE chat_id=$1",
            chat_id
        )

async def list_group_bans():
    async with db.pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM group_bans")
