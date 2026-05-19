"""
/mediasetup — Owner command to (re-)cache all game media files for clone bots.

Run this once after adding new videos or if clone bots aren't showing animations.
The bot will attempt to send each source file_id to your DM, download it,
and save it to /tmp/nexora_media/ for all clone bots to use.
"""
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from utils.media_downloader import (
    MEDIA_DIR,
    _iter_all_sources,
    download_single,
)


@Client.on_message(
    filters.command("mediasetup") & filters.private & filters.user(list(Config.OWNER_IDS))
)
async def mediasetup_cmd(client: Client, message: Message):
    if Config.IS_CLONE:
        return await message.reply_text("❌ Run this on the main bot only.")

    progress = await message.reply_text(
        "🔧 <b>Media Setup Starting…</b>\n\n"
        "Attempting to download all game videos/GIFs to disk.\n"
        "This lets clone bots display the same animations. Please wait…",
        parse_mode=ParseMode.HTML,
    )

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    owner_id   = message.from_user.id
    ok_count   = 0
    fail_count = 0
    failed_keys = []

    sources = list(_iter_all_sources())
    total   = len(sources)

    for i, (disk_key, file_id) in enumerate(sources, 1):
        if i % 5 == 0 or i == total:
            try:
                await progress.edit_text(
                    f"🔧 <b>Media Setup</b>\n\n"
                    f"Processing {i}/{total}…\n"
                    f"✅ Saved: {ok_count}  ❌ Failed: {fail_count}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

        ok = await download_single(client, disk_key, file_id, owner_id)
        if ok:
            ok_count += 1
        else:
            fail_count += 1
            failed_keys.append(disk_key)

    # Build result message
    if fail_count == 0:
        summary = (
            f"✅ <b>Media Setup Complete!</b>\n\n"
            f"<b>{ok_count}</b> files saved to disk.\n"
            f"Clone bots will now display animations correctly. 🎉"
        )
    else:
        failed_list = "\n".join(f"  • <code>{k}</code>" for k in failed_keys[:10])
        if len(failed_keys) > 10:
            failed_list += f"\n  … and {len(failed_keys) - 10} more"
        summary = (
            f"⚠️ <b>Media Setup Partial</b>\n\n"
            f"✅ Saved: <b>{ok_count}</b> files\n"
            f"❌ Failed: <b>{fail_count}</b> files\n\n"
            f"<b>Failed keys:</b>\n{failed_list}\n\n"
            f"<i>Failed files may have been uploaded by a different bot token. "
            f"Use /addmedia to re-upload them fresh.</i>"
        )

    try:
        await progress.edit_text(summary, parse_mode=ParseMode.HTML)
    except Exception:
        await message.reply_text(summary, parse_mode=ParseMode.HTML)


@Client.on_message(
    filters.command("mediainfo") & filters.private & filters.user(list(Config.OWNER_IDS))
)
async def mediainfo_cmd(client: Client, message: Message):
    """Show disk cache status."""
    if Config.IS_CLONE:
        return await message.reply_text("❌ Main bot only.")

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    sources   = list(_iter_all_sources())
    present   = sum(1 for k, _ in sources if (MEDIA_DIR / f"{k}.bin").exists())
    missing   = len(sources) - present
    disk_mb   = sum(
        (MEDIA_DIR / f"{k}.bin").stat().st_size
        for k, _ in sources
        if (MEDIA_DIR / f"{k}.bin").exists()
    ) / (1024 * 1024)

    lines = [
        "📦 <b>Media Cache Status</b>\n",
        f"✅ On disk: <b>{present}</b> / {len(sources)} files",
        f"❌ Missing: <b>{missing}</b> files",
        f"💾 Disk usage: <b>{disk_mb:.1f} MB</b>\n",
    ]

    if missing:
        lines.append("Run /mediasetup to download missing files.")
    else:
        lines.append("All files are cached. Clone bots will show animations! 🎉")

    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
