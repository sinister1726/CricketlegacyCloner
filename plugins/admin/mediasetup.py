"""
Owner media management commands:

  /addfile <key>   — reply to a video/GIF to register it as a game animation
  /listmedia       — show all custom media registered in the DB
  /removefile <key> <file_id> — remove a specific file_id from a key
  /mediasetup      — download all source files to disk (for clone bots)
  /mediainfo       — show disk cache status
"""
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import Config

# ── valid key sets ────────────────────────────────────────────────────────────
_RUN_KEYS = {"0", "1", "2", "3", "4", "5", "6", "out", "batting", "bowling", "opening"}
_ACH_KEYS = {"50", "100", "150", "250", "3", "5", "hat_trick", "duck"}

_KEY_HELP = (
    "<b>Valid keys:</b>\n"
    "<b>Run animations:</b>  <code>0 1 2 3 4 5 6 Out Batting Bowling Opening</code>\n"
    "<b>Achievement:</b>     <code>achieve_50 achieve_100 achieve_HAT_TRICK achieve_Duck</code>"
)


def _parse_key(raw: str) -> tuple[str, str] | None:
    """
    Parse user-supplied key into (category, canonical_key) or None if invalid.
    Examples:
        "6"            → ("run", "6")
        "Out"          → ("run", "Out")
        "achieve_50"   → ("achieve", 50)
        "achieve_HAT_TRICK" → ("achieve", "HAT_TRICK")
    """
    r = raw.strip()

    if r.lower().startswith("achieve_"):
        sub = r[len("achieve_"):]
        # Normalise numeric achieve keys
        try:
            sub = int(sub)
        except ValueError:
            sub = sub.upper()
            if sub == "DUCK":
                sub = "Duck"
            elif sub == "HAT_TRICK":
                sub = "HAT_TRICK"
        return ("achieve", sub)

    # Run key — case-insensitive match to canonical name
    lower = r.lower()
    canonical_map = {
        "0": "0", "1": "1", "2": "2", "3": "3",
        "4": "4", "5": "5", "6": "6",
        "out": "Out", "batting": "Batting",
        "bowling": "Bowling", "opening": "Opening",
    }
    if lower in canonical_map:
        return ("run", canonical_map[lower])

    return None


def _get_file_id(message: Message) -> tuple[str | None, str | None]:
    """Extract (file_id, media_type) from a message."""
    if message.video:
        return message.video.file_id, "video 🎥"
    if message.animation:
        return message.animation.file_id, "GIF 🎞"
    if message.document:
        return message.document.file_id, "document 📄"
    if message.video_note:
        return message.video_note.file_id, "video note ⭕"
    return None, None


# ── /addfile ──────────────────────────────────────────────────────────────────

@Client.on_message(
    filters.command("addfile") & filters.user(list(Config.OWNER_IDS))
)
async def addfile_cmd(client: Client, message: Message):
    if Config.IS_CLONE:
        return await message.reply_text("❌ Run this on the main bot only.")

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text(
            "❓ <b>Usage:</b> reply to a video/GIF and send:\n"
            "<code>/addfile &lt;key&gt;</code>\n\n"
            + _KEY_HELP,
            parse_mode=ParseMode.HTML,
        )

    raw_key = args[1].strip()
    parsed  = _parse_key(raw_key)
    if parsed is None:
        return await message.reply_text(
            f"❌ Unknown key <code>{raw_key}</code>\n\n{_KEY_HELP}",
            parse_mode=ParseMode.HTML,
        )
    category, key = parsed

    # Must be a reply to a media message
    reply = message.reply_to_message
    if not reply:
        return await message.reply_text(
            "❌ Reply to a <b>video or GIF</b> with this command.",
            parse_mode=ParseMode.HTML,
        )

    file_id, media_type = _get_file_id(reply)
    if not file_id:
        return await message.reply_text(
            "❌ The replied message doesn't contain a video, GIF, or document.",
            parse_mode=ParseMode.HTML,
        )

    # Save to DB
    from database.game_media import add_media_id
    updated = await add_media_id(category, key, file_id)

    # Also download to disk for clone bots
    from utils.media_downloader import MEDIA_DIR, download_single
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    safe_k   = str(key).replace(" ", "_").replace("/", "-")
    disk_key = f"{category}_{safe_k}_{len(updated) - 1}"
    disk_ok  = await download_single(client, disk_key, file_id, message.chat.id)

    # Clear stale clone caches for this key so they re-upload the fresh file
    from database.media_cache import clear_media_key_for_all
    await clear_media_key_for_all(f"{category}_{safe_k}")

    status_disk = "✅ saved to disk" if disk_ok else "⚠️ disk save failed (clone bots will re-upload on first use)"

    await message.reply_text(
        f"✅ <b>File registered!</b>\n\n"
        f"🔑 Key: <code>{category}/{key}</code>\n"
        f"📎 Type: {media_type}\n"
        f"🆔 File ID: <code>{file_id[:40]}…</code>\n"
        f"💾 Disk: {status_disk}\n"
        f"📦 Total for this key: <b>{len(updated)}</b>\n\n"
        f"The animation will now play during games. 🏏",
        parse_mode=ParseMode.HTML,
    )


# ── /listmedia ────────────────────────────────────────────────────────────────

@Client.on_message(
    filters.command("listmedia") & filters.user(list(Config.OWNER_IDS))
)
async def listmedia_cmd(client: Client, message: Message):
    if Config.IS_CLONE:
        return await message.reply_text("❌ Main bot only.")

    from database.game_media import list_all_media

    docs = await list_all_media()
    if not docs:
        return await message.reply_text(
            "📭 No custom media registered yet.\n"
            "Use /addfile to add videos.",
            parse_mode=ParseMode.HTML,
        )

    lines = ["📦 <b>Custom Game Media</b>\n"]
    for doc in sorted(docs, key=lambda d: d["_id"]):
        count = len(doc.get("ids", []))
        lines.append(f"• <code>{doc['_id']}</code> — <b>{count}</b> file(s)")
    lines.append(f"\n<i>Total: {len(docs)} keys</i>")

    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── /removefile ───────────────────────────────────────────────────────────────

@Client.on_message(
    filters.command("removefile") & filters.user(list(Config.OWNER_IDS))
)
async def removefile_cmd(client: Client, message: Message):
    if Config.IS_CLONE:
        return await message.reply_text("❌ Main bot only.")

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return await message.reply_text(
            "❓ <b>Usage:</b> <code>/removefile &lt;key&gt; &lt;file_id&gt;</code>",
            parse_mode=ParseMode.HTML,
        )

    raw_key = parts[1].strip()
    file_id = parts[2].strip()
    parsed  = _parse_key(raw_key)
    if parsed is None:
        return await message.reply_text(f"❌ Unknown key <code>{raw_key}</code>", parse_mode=ParseMode.HTML)

    category, key = parsed
    from database.game_media import remove_media_id
    remaining = await remove_media_id(category, key, file_id)

    await message.reply_text(
        f"🗑 Removed from <code>{category}/{key}</code>.\n"
        f"Remaining: <b>{len(remaining)}</b> file(s)",
        parse_mode=ParseMode.HTML,
    )


# ── /mediasetup ───────────────────────────────────────────────────────────────

@Client.on_message(
    filters.command("mediasetup") & filters.private & filters.user(list(Config.OWNER_IDS))
)
async def mediasetup_cmd(client: Client, message: Message):
    if Config.IS_CLONE:
        return await message.reply_text("❌ Run this on the main bot only.")

    from utils.media_downloader import MEDIA_DIR, _iter_all_sources, download_single

    progress = await message.reply_text(
        "🔧 <b>Media Setup Starting…</b>\n\n"
        "Downloading all game videos/GIFs to disk so clone bots can use them…",
        parse_mode=ParseMode.HTML,
    )

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    dump_target = message.chat.id     # owner's DM — guaranteed to work here
    ok_count    = 0
    fail_keys   = []
    sources     = list(_iter_all_sources())

    for i, (disk_key, file_id) in enumerate(sources, 1):
        if i % 5 == 0 or i == len(sources):
            try:
                await progress.edit_text(
                    f"🔧 <b>Media Setup</b>  {i}/{len(sources)}\n"
                    f"✅ Saved: {ok_count}  ❌ Failed: {len(fail_keys)}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        if await download_single(client, disk_key, file_id, dump_target):
            ok_count += 1
        else:
            fail_keys.append(disk_key)

    if not fail_keys:
        result = f"✅ <b>Done!</b> {ok_count} files saved — clone bots will now show animations! 🎉"
    else:
        result = (
            f"⚠️ <b>Partial:</b> {ok_count} saved, {len(fail_keys)} failed.\n\n"
            f"Failed keys need fresh uploads — use /addfile to replace them."
        )

    try:
        await progress.edit_text(result, parse_mode=ParseMode.HTML)
    except Exception:
        await message.reply_text(result, parse_mode=ParseMode.HTML)


# ── /mediainfo ────────────────────────────────────────────────────────────────

@Client.on_message(
    filters.command("mediainfo") & filters.private & filters.user(list(Config.OWNER_IDS))
)
async def mediainfo_cmd(client: Client, message: Message):
    if Config.IS_CLONE:
        return await message.reply_text("❌ Main bot only.")

    from utils.media_downloader import MEDIA_DIR, _iter_all_sources
    from database.game_media import list_all_media

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    sources  = list(_iter_all_sources())
    present  = sum(1 for k, _ in sources if (MEDIA_DIR / f"{k}.bin").exists())
    disk_mb  = sum(
        (MEDIA_DIR / f"{k}.bin").stat().st_size
        for k, _ in sources
        if (MEDIA_DIR / f"{k}.bin").exists()
    ) / (1024 * 1024)

    custom_docs = await list_all_media()
    custom_keys = len(custom_docs)
    custom_fids = sum(len(d.get("ids", [])) for d in custom_docs)

    lines = [
        "📦 <b>Media Cache Status</b>\n",
        f"💾 On disk: <b>{present}</b> / {len(sources)} source files ({disk_mb:.1f} MB)",
        f"🗄 Custom DB: <b>{custom_keys}</b> keys, <b>{custom_fids}</b> file_id(s)\n",
    ]
    if present < len(sources):
        lines.append("Run /mediasetup to download missing files.")
    else:
        lines.append("All source files on disk ✅")
    if custom_keys:
        lines.append(f"Custom files active — /listmedia to view them.")

    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
