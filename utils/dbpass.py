import asyncio
import asyncpg
from database.connection import db

async def safe_fetchrow(query, *args, retries=2):
    for attempt in range(retries + 1):
        try:
            async with db.pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except asyncpg.exceptions.ConnectionDoesNotExistError:
            if attempt >= retries: raise
            await asyncio.sleep(0.2)

async def safe_fetch(query, *args, retries=2):
    for attempt in range(retries + 1):
        try:
            async with db.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except asyncpg.exceptions.ConnectionDoesNotExistError:
            if attempt >= retries: raise
            await asyncio.sleep(0.2)

async def safe_execute(query, *args, retries=2):
    for attempt in range(retries + 1):
        try:
            async with db.pool.acquire() as conn:
                return await conn.execute(query, *args)
        except asyncpg.exceptions.ConnectionDoesNotExistError:
            if attempt >= retries: raise
            await asyncio.sleep(0.2)
            
