from database.connection import db

async def restrict_user(user_id: int, reason: str, admin_id: int):
    async with db.pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS restricted_users (
                user_id BIGINT PRIMARY KEY,
                reason TEXT,
                admin_id BIGINT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            INSERT INTO restricted_users (user_id, reason, admin_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason, admin_id = EXCLUDED.admin_id
        """, user_id, reason, admin_id)

async def unrestrict_user(user_id: int):
    async with db.pool.acquire() as conn:
        await conn.execute("DELETE FROM restricted_users WHERE user_id = $1", user_id)

async def get_restriction_reason(user_id: int):
    try:
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT reason FROM restricted_users WHERE user_id = $1", user_id)
            if row:
                return row["reason"]
    except Exception:
        pass 
    return None
  
