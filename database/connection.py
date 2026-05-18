import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

# Collections that are GLOBAL across all bots — never prefixed in clone bots.
_GLOBAL_COLLECTIONS = frozenset({
    "user_premium",
    "user_clones",
    "clone_settings",
    "bot_settings",
})


class _PrefixedDB:
    """
    A thin proxy around a Motor database that automatically prefixes
    collection names with `prefix`, EXCEPT for the shared global collections.

    This allows clone bots to have fully isolated stats/users/groups while
    still sharing the same MongoDB instance as the main bot.
    """

    def __init__(self, real_db, prefix: str):
        self._real   = real_db
        self._prefix = prefix

    # All collection access goes through __getitem__
    def __getitem__(self, name: str):
        if name in _GLOBAL_COLLECTIONS:
            return self._real[name]
        return self._real[f"{self._prefix}{name}"]

    # Pass-through for Motor database methods (list_collection_names, etc.)
    def __getattr__(self, name: str):
        return getattr(self._real, name)


class Database:
    def __init__(self):
        self.client = None
        self.db     = None

    async def connect(self, retries: int = 10, delay: float = 3.0):
        for attempt in range(1, retries + 1):
            try:
                print(f"🗄️ Connecting to MongoDB... (attempt {attempt}/{retries})")
                self.client = AsyncIOMotorClient(Config.MONGO_URL)
                real_db     = self.client.get_default_database()
                await self.client.admin.command("ping")
                print("✅ MongoDB Connected.")

                prefix = Config.CLONE_DB_PREFIX
                if prefix:
                    self.db = _PrefixedDB(real_db, prefix)
                    print(f"🧬 Clone DB prefix active: '{prefix}*'")
                else:
                    self.db = real_db
                return
            except Exception as e:
                print(f"⚠️ DB connect attempt {attempt} failed: {e}")
                if attempt < retries:
                    wait = delay * attempt
                    print(f"🔄 Retrying in {wait:.0f}s…")
                    await asyncio.sleep(wait)
        print("❌ Could not connect to MongoDB after all retries.")

    async def ensure_pool(self):
        if not self.client:
            await self.connect(retries=5, delay=2.0)

    async def close(self):
        if self.client:
            self.client.close()
            self.client = None
            self.db     = None

    # ── Convenience: direct access to the real underlying DB ─────────────────
    # Used by /transferclone to read clone collections from the main bot.
    @property
    def real_db(self):
        if isinstance(self.db, _PrefixedDB):
            return self.db._real
        return self.db


db = Database()
