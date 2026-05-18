import os


class Config:
    # Telegram API
    API_ID   = int(os.getenv("API_ID", "25887786"))
    API_HASH = os.getenv("API_HASH", "e4201277f5f2883f22c150167bd24479")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")

    # Database
    MONGO_URL = os.getenv(
        "MONGO_URL",
        "mongodb+srv://bsdk:betichod@cluster0.fgj1r9z.mongodb.net/Cricketlegacy?retryWrites=true&w=majority",
    )

    # Bot Info
    BOT_USERNAME = os.getenv("BOT_USERNAME", "@CricketLegacy2Bot")
    SUPPORT_GROUP = os.getenv("SUPPORT_GROUP",  "https://t.me/+joF1bCfiMT9jMzVh")
    PLAY_ZONE_INFO = os.getenv("PLAY_ZONE_INFO", "https://t.me/+joF1bCfiMT9jMzVh")

    # Owners
    OWNER_IDS = {
        int(x) for x in os.getenv("OWNER_IDS", "8186068163").split()
    }

    # GitHub
    GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
    UPSTREAM_REPO  = os.getenv(
        "UPSTREAM_REPO",
        "https://github.com/drexocoder-source/Cricsssketlegssacys",
    )

    # AI / NVIDIA
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")

    # Images
    START_IMAGE = os.getenv(
        "START_IMAGE",
        "https://graph.org/file/a37d935e98e4c92e04cee-c1871cfafb3f808563.jpg",
    )

    # Logs
    LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", "-1003692127639"))

    # ── Clone Bot System ──────────────────────────────────────────────────────
    IS_CLONE       = os.getenv("IS_CLONE", "0") == "1"
    CLONE_OWNER_ID = (
        int(os.getenv("CLONE_OWNER_ID", "0"))
        if os.getenv("CLONE_OWNER_ID", "0") != "0"
        else None
    )
    MAIN_BOT_USERNAME      = os.getenv("MAIN_BOT_USERNAME",      "@LegacyCloneProRO_BOT")
    MAIN_SUPPORT           = os.getenv("MAIN_SUPPORT",           "https://t.me/clg_fun_zone")
    MAIN_SUPPORT_USERNAME  = os.getenv("MAIN_SUPPORT_USERNAME",  "@clg_fun_zone")

    # Collection prefix for clone bots — set automatically when spawning.
    # Empty string = main bot (no prefix).
    CLONE_DB_PREFIX = os.getenv("CLONE_DB_PREFIX", "")
