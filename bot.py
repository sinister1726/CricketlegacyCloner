import asyncio
from pyrogram import Client, idle
from config import Config
from database.connection import db
from database.migrate import migrate

async def initialize_database():
    """Call this inside your main bot startup function."""
    await db.connect()
    await migrate()
    print("✅ Database connected & tables ready")

async def start_nexora():
    # 1. Initialize the Bot FIRST (let Pyrogram own the loop)
    bot = Client(
        "bot",
        bot_token=Config.BOT_TOKEN,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        workers=80,
        plugins=dict(root="plugins")
    )

    # 2. Start the Client
    await bot.start()
    print("🚀 Nexora Cricket Bot is Online!")

    # 3. Initialize Database AFTER bot is running
    try:
        await initialize_database()
    except Exception as e:
        print(f"❌ Database Initialization Failed: {e}")

    # 🔌 GLOBAL CLIENT FALLBACK (ENGINE SAFETY)
    from plugins.game.team.init import ACTIVE_MATCHES
    for m in ACTIVE_MATCHES.values():
        if not m.get("client"):
            m["client"] = bot

    # 4. Keep it running
    await idle()

    # 5. Graceful Shutdown
    print("🛑 Shutting down...")
    await bot.stop()
    await db.close()

if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(start_nexora())
    except KeyboardInterrupt:
        print("👋 Bot stopped manually.")
