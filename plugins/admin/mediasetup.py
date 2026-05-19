"""
Owner media management commands (work in DM and groups):

  /addfile <key>              — reply to a video/GIF to register it
  /listmedia                  — show all custom media keys in DB
  /removefile <key> <file_id> — remove a specific file_id from a key
  /mediasetup                 — download all source files to disk (for clone bots)
  /mediainfo                  — show disk cache status
"""
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import Config

_OWNER_FILTER = filters.user(list(Config.OWNER_IDS))
_ANYWHERE     = filters.private | filters.group

# ── valid key sets ────────────────────────────────────────────────────────────
_KEY_HELP = (
    "<b>Run keys:</b>  <code>0 1 2 3 4 5 6 Out Batting Bowling Opening</code>\n"
    "<b>Achieve keys:</b>  <code>achieve_50  achieve_HAT_TRICK  achieve_Duck</code>"
)


def _parse_key(raw: str) -> tuple[str, str | int] | None:
    r = raw.strip()
    if r.lower().startswith("achieve_"):
        sub = r[len("achieve_"):]
        try:
            return ("achieve", int(sub))
        except ValueError:
            s = sub.upper()
            if s == "DUCK":       s = "Duck"
            elif s == "HAT_TRICK": s = "HAT_TRICK"
            return ("achieve", s)
    canonical = {
        "0":"0","1":"1","2":"2","3":"3","4":"4","5":"5","6":"6",
        "out":"Out","batting":"Batting","bowling":"Bowling","opening":"Opening",
    }
    c = canonical.get(r.lower())
    return ("run", c) if c else None


def _get_file_id(message: Message) -> tuple[str | None, str]:
    if message.video:       return message.video.file_id,      "video 🎥"
    if message.animation:   return message.animation.file_id,  "GIF 🎞"
    if message.document:    return message.document.file_id,   "document 📄"
    if message.video_note:  return message.video_note.file_id, "video note ⭕"
    return None, ""


# ── /addfile ──────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("addfile") & _ANYWHERE & _OWNER_FILTER)
async def addfile_cmd(client: Client, message: Message):
    if Config.IS_CLONE:
        return await message.reply_text("❌ Run this on the main bot only.")

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text(
            "❓ Reply to a video/GIF and send <code>/addfile &lt;key&gt;</code>\n\n" + _KEY_HELP,
            parse_mode=ParseMode.HTML,
        )

    parsed = _parse_key(args[1])
    if not parsed:
        return await message.reply_text(
            f"❌ Unknown key <code>{args[1]}</code>\n\n{_KEY_HELP}",
            parse_mode=ParseMode.HTML,
        )
    category, key = parsed

    reply = message.reply_to_message
    if not reply:
        return await message.reply_text("❌ Reply to a <b>video or GIF</b> with this command.", parse_mode=ParseMode.HTML)

    file_id, media_type = _get_file_id(reply)
    if not file_id:
        return await message.reply_text("❌ No video, GIF, or document found in that message.")

    from database.game_media import add_media_id
    updated = await add_media_id(category, key, file_id)

    # Save to disk for clone bots
    from utils.media_downloader import MEDIA_DIR, download_single
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    safe_k   = str(key).replace(" ", "_")
    disk_key = f"{category}_{safe_k}_{len(updated) - 1}"
    disk_ok  = await download_single(client, disk_key, file_id, message.chat.id)

    # Invalidate clone caches so they re-upload the new file
    from database.media_cache import clear_media_key_for_all
    await clear_media_key_for_all(f"{category}_{safe_k}")

    disk_note = "✅ saved to disk" if disk_ok else "⚠️ disk save skipped (clones auto-upload on first use)"

    await message.reply_text(
        f"✅ <b>File registered!</b>\n\n"
        f"🔑  Key: <code>{category}/{key}</code>\n"
        f"📎  Type: {media_type}\n"
        f"🆔  ID: <code>{file_id[:38]}…</code>\n"
        f"💾  Disk: {disk_note}\n"
        f"📦  Total for this key: <b>{len(updated)}</b>",
        parse_mode=ParseMode.HTML,
    )


# ── /listmedia ────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("listmedia") & _ANYWHERE & _OWNER_FILTER)
async def listmedia_cmd(client: Client, message: Message):
    if Config.IS_CLONE:
        return await message.reply_text("❌ Main bot only.")

    from database.game_media import list_all_media
    docs = await list_all_media()
    if not docs:
        return await message.reply_text("📭 No custom media yet. Use /addfile to add videos.")

    lines = ["📦 <b>Custom Game Media</b>\n"]
    for doc in sorted(docs, key=lambda d: d["_id"]):
        lines.append(f"• <code>{doc['_id']}</code>  —  <b>{len(doc.get('ids',[]))}</b> file(s)")
    lines.append(f"\n<i>{len(docs)} keys total</i>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── /removefile ───────────────────────────────────────────────────────────────
@Client.on_message(filters.command("removefile") & _ANYWHERE & _OWNER_FILTER)
async def removefile_cmd(client: Client, message: Message):
    if Config.IS_CLONE:
        return await message.reply_text("❌ Main bot only.")

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return await message.reply_text("❓ Usage: <code>/removefile &lt;key&gt; &lt;file_id&gt;</code>", parse_mode=ParseMode.HTML)

    parsed = _parse_key(parts[1])
    if not parsed:
        return await message.reply_text(f"❌ Unknown key <code>{parts[1]}</code>", parse_mode=ParseMode.HTML)

    category, key = parsed
    from database.game_media import remove_media_id
    remaining = await remove_media_id(category, key, parts[2].strip())
    await message.reply_text(
        f"🗑  Removed from <code>{category}/{key}</code>. Remaining: <b>{len(remaining)}</b>",
        parse_mode=ParseMode.HTML,
    )


# ── /mediasetup ───────────────────────────────────────────────────────────────
@Client.on_message(filters.command("mediasetup") & _ANYWHERE & _OWNER_FILTER)
async def mediasetup_cmd(client: Client, message: Message):
    if Config.IS_CLONE:
        return await message.reply_text("❌ Run this on the main bot only.")

    from utils.media_downloader import MEDIA_DIR, _iter_all_sources, download_single

    progress = await message.reply_text(
        "🔧 <b>Media Setup</b>\n\nDownloading game videos to disk for clone bots…",
        parse_mode=ParseMode.HTML,
    )

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    dump   = message.chat.id
    ok     = 0
    failed = []
    srcs   = list(_iter_all_sources())

    for i, (disk_key, file_id) in enumerate(srcs, 1):
        if i % 4 == 0 or i == len(srcs):
            try:
                await progress.edit_text(
                    f"🔧 <b>Media Setup</b>  {i}/{len(srcs)}\n"
                    f"✅ {ok}  saved   ❌ {len(failed)}  failed",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        if await download_single(client, disk_key, file_id, dump):
            ok += 1
        else:
            failed.append(disk_key)

    result = (
        f"✅ <b>Done!</b>  {ok} files saved to disk.\nClone bots will now show animations! 🎉"
        if not failed else
        f"⚠️ <b>Partial:</b>  {ok} saved,  {len(failed)} failed.\n\n"
        f"Use /addfile to replace failed files with fresh uploads."
    )
    try:
        await progress.edit_text(result, parse_mode=ParseMode.HTML)
    except Exception:
        await message.reply_text(result, parse_mode=ParseMode.HTML)


# ── /mediainfo ────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("mediainfo") & _ANYWHERE & _OWNER_FILTER)
async def mediainfo_cmd(client: Client, message: Message):
    if Config.IS_CLONE:
        return await message.reply_text("❌ Main bot only.")

    from utils.media_downloader import MEDIA_DIR, _iter_all_sources
    from database.game_media import list_all_media

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    srcs    = list(_iter_all_sources())
    present = sum(1 for k, _ in srcs if (MEDIA_DIR / f"{k}.bin").exists())
    mb      = sum(
        (MEDIA_DIR / f"{k}.bin").stat().st_size
        for k, _ in srcs if (MEDIA_DIR / f"{k}.bin").exists()
    ) / (1024 * 1024)

    docs   = await list_all_media()
    c_keys = len(docs)
    c_fids = sum(len(d.get("ids", [])) for d in docs)

    lines = [
        "📦 <b>Media Cache Status</b>\n",
        f"💾  On disk:  <b>{present}</b> / {len(srcs)} files  ({mb:.1f} MB)",
        f"🗄  Custom DB: <b>{c_keys}</b> keys · <b>{c_fids}</b> file_id(s)",
        "",
        ("✅ All source files cached." if present >= len(srcs) else "⚠️ Run /mediasetup to download missing files."),
    ]
    if c_keys:
        lines.append("/listmedia to view custom files.")

    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
