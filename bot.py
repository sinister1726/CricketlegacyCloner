import asyncio
import time
import httpx
from pyrogram import Client, idle
from pyrogram.enums import ParseMode
from config import Config
from database.connection import db
from database.migrate import migrate

LOG_CHANNEL = Config.LOG_CHANNEL


async def _db_watchdog():
    while True:
        await asyncio.sleep(15)
        if not db.client:
            print("🔌 DB watchdog: pool is gone, reconnecting…")
            await db.connect(retries=5, delay=3.0)

async def initialize_database():
    await db.connect()
    await migrate()
    try:
        from database.settings import load_settings
        await load_settings(force=True)
        print("✅ Settings loaded")
    except Exception as e:
        print(f"⚠️ Settings load failed: {e}")
    print("✅ Database connected & tables ready")

async def _set_clone_description():
    """Set the clone bot's description to credit the main bot."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            desc = (
                f"🧬 Clone of {Config.MAIN_BOT_USERNAME}\n"
                f"🏏 Cricket game bot — play in your groups!\n"
                f"💬 Support: {Config.MAIN_SUPPORT_USERNAME}"
            )
            short_desc = f"Cricket game bot · Clone of {Config.MAIN_BOT_USERNAME}"
            await c.post(
                f"https://api.telegram.org/bot{Config.BOT_TOKEN}/setMyDescription",
                json={"description": desc},
            )
            await c.post(
                f"https://api.telegram.org/bot{Config.BOT_TOKEN}/setMyShortDescription",
                json={"short_description": short_desc},
            )
        print("✅ Clone bot description set.")
    except Exception as e:
        print(f"⚠️ Could not set clone description: {e}")

async def start_nexora():

    start_time = time.time()

    bot = Client(
        "bot" if not Config.IS_CLONE else f"clone_{Config.CLONE_OWNER_ID}",
        bot_token=Config.BOT_TOKEN,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        workers=80,
        plugins=dict(root="plugins")
    )

    try:
        await initialize_database()
    except Exception as e:
        print(f"❌ Database Initialization Failed: {e}")

    await bot.start()

    boot_speed = round(time.time() - start_time, 2)

    print("🚀 Nexora Cricket Bot is Online!")

    if Config.IS_CLONE:
        await _set_clone_description()

    try:
        me = await bot.get_me()

        if Config.IS_CLONE:
            startup_text = (
                f"🧬 <b>ᴄʟᴏɴᴇ ʙᴏᴛ ᴏɴʟɪɴᴇ</b>\n\n"
                "━━━━━━━━━━━━━━━\n"
                f"🤖 <b>Bot :</b> {me.first_name}\n"
                f"🆔 <b>ID :</b> <code>{me.id}</code>\n"
                f"👤 <b>Owner :</b> <code>{Config.CLONE_OWNER_ID}</code>\n"
                f"⚡ <b>Startup Speed :</b> {boot_speed}s\n"
                f"🔗 <b>Main Bot :</b> {Config.MAIN_BOT_USERNAME}\n"
                "━━━━━━━━━━━━━━━"
            )
        else:
            startup_text = (
                "🚀 <b>ʟᴇɢᴀᴄʏ ʙᴏᴛ ɪꜱ ᴏɴʟɪɴᴇ</b>\n\n"
                "━━━━━━━━━━━━━━━\n"
                f"🤖 <b>Bot :</b> {me.first_name}\n"
                f"🆔 <b>ID :</b> <code>{me.id}</code>\n"
                f"⚡ <b>Startup Speed :</b> {boot_speed}s\n"
                f"🧠 <b>Workers :</b> 80\n"
                f"🗄 <b>Database :</b> Connected\n"
                f"🌐 <b>Status :</b> Running\n"
                "━━━━━━━━━━━━━━━\n"
                "✨ <b>ʟᴇɢᴀᴄʏ ᴘᴏᴡᴇʀᴇᴅ</b>"
            )

        await bot.send_message(
            LOG_CHANNEL,
            startup_text,
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        print("Log channel error:", e)

    from plugins.game.team import ACTIVE_MATCHES
    for m in ACTIVE_MATCHES.values():
        if not m.get("client"):
            m["client"] = bot

    asyncio.create_task(_db_watchdog())
    print("🔌 Database watchdog active.")

    from plugins.game.team.cleanup import auto_clean_matches
    asyncio.create_task(auto_clean_matches(bot))
    print("🧹 Background Garbage Collector is active!")

    from plugins.game.solo.cleanup import auto_clean_solo
    asyncio.create_task(auto_clean_solo(bot))
    print("🧹 Solo Background Cleaner is active!")

    from plugins.utilities.nudge import start_nudge_task
    start_nudge_task(bot)

    async def _premium_expiry_loop():
        from database.premium import check_and_expire_all
        while True:
            await asyncio.sleep(3600)
            await check_and_expire_all()

    asyncio.create_task(_premium_expiry_loop())
    print("⏰ Premium expiry checker active (hourly).")

    if not Config.IS_CLONE:
        async def _clone_expiry_loop():
            from database.clone import check_and_expire_clones
            while True:
                await asyncio.sleep(3600)
                await check_and_expire_clones(bot)

        asyncio.create_task(_clone_expiry_loop())
        print("⏰ Clone premium expiry checker active (hourly).")

        from plugins.admin.clone_mgmt import respawn_all_clones
        asyncio.create_task(respawn_all_clones())

    await idle()

    print("🛑 Shutting down...")
    await bot.stop()
    await db.close()

if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(start_nexora())
    except KeyboardInterrupt:
        print("👋 Bot stopped manually.")
