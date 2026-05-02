import os
import sys
import json
import time
import html
import asyncio
import platform
from datetime import datetime
from io import BytesIO

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
)

from config import Config
from database.connection import db


OWNER_FILTER = filters.user(list(Config.OWNER_IDS))
PANEL_START = time.time()


def _is_owner(user_id: int) -> bool:
    return user_id in Config.OWNER_IDS


def _human_uptime(seconds: float) -> str:
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def _human_bytes(num: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024:
            return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} PB"


def _json_default(obj):
    if isinstance(obj, datetime):
        return {"$date": obj.isoformat()}
    try:
        from bson import ObjectId
        if isinstance(obj, ObjectId):
            return str(obj)
    except Exception:
        pass
    return str(obj)


def _panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 DB Stats", callback_data="own:dbstats"),
                InlineKeyboardButton("🖥 Server", callback_data="own:server"),
            ],
            [
                InlineKeyboardButton("💾 Backup All", callback_data="own:backup_all"),
                InlineKeyboardButton("⏱ Uptime", callback_data="own:uptime"),
            ],
            [
                InlineKeyboardButton("📡 Broadcast Help", callback_data="own:broad"),
            ],
            [
                InlineKeyboardButton("♻️ Restart Bot", callback_data="own:restart_ask"),
                InlineKeyboardButton("✖ Close", callback_data="own:close"),
            ],
        ]
    )


def _panel_text() -> str:
    return (
        "👑 <b>OWNER CONTROL PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Maintenance</b>\n"
        "• /maintenance – Show status\n"
        "• /maintenance on <code>[reason]</code> – Pause game commands\n"
        "• /maintenance off – Resume\n\n"
        "<b>Database</b>\n"
        "• /dbbackup <code>[collection|all]</code> – Export Mongo → JSON\n"
        "• /dbstats – Collection counts &amp; sizes\n"
        "• /dbcollections – List all collections\n"
        "• /transfer <code>postgres://…</code> – PG → Mongo (+ JSON dump)\n"
        "• /dbtrans <code>collection</code> – Import JSON → Mongo (reply file)\n\n"
        "<b>System</b>\n"
        "• /serverinfo – Host, RAM, CPU, disk\n"
        "• /uptime – Bot &amp; panel uptime\n"
        "• /restart – Restart the bot process\n"
        "• /logs <code>[n]</code> – Tail recent log lines\n\n"
        "<b>Moderation</b>\n"
        "• /restrict · /unrestrict · /restricted\n"
        "• /broad <code>-forward|-copy|-users|-groups</code>\n\n"
        "<b>Other</b>\n"
        "• /active – Active matches\n"
        "• /leave <code>chat_id</code> – Make the bot leave a chat\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )


# ───────────────────────── /owner ─────────────────────────

@Client.on_message(filters.command("owner") & OWNER_FILTER)
async def owner_panel_cmd(client: Client, message: Message):
    await message.reply_text(
        _panel_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=_panel_kb(),
        disable_web_page_preview=True,
    )


# ───────────────────────── /uptime ─────────────────────────

@Client.on_message(filters.command("uptime") & OWNER_FILTER)
async def uptime_cmd(client: Client, message: Message):
    await message.reply_text(
        f"⏱ <b>Uptime:</b> <code>{_human_uptime(time.time() - PANEL_START)}</code>",
        parse_mode=ParseMode.HTML,
    )


# ───────────────────────── /serverinfo ─────────────────────────

async def _server_info_text() -> str:
    try:
        import shutil
        disk = shutil.disk_usage("/")
        disk_line = f"{_human_bytes(disk.used)} / {_human_bytes(disk.total)}"
    except Exception:
        disk_line = "n/a"

    try:
        with open("/proc/meminfo") as f:
            meminfo = {
                line.split(":")[0]: line.split(":")[1].strip()
                for line in f
            }
        mem_total = meminfo.get("MemTotal", "n/a")
        mem_free = meminfo.get("MemAvailable", "n/a")
        mem_line = f"{mem_free} free / {mem_total}"
    except Exception:
        mem_line = "n/a"

    try:
        load = os.getloadavg()
        load_line = f"{load[0]:.2f} {load[1]:.2f} {load[2]:.2f}"
    except Exception:
        load_line = "n/a"

    return (
        "🖥 <b>SERVER INFO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Host:</b> <code>{html.escape(platform.node())}</code>\n"
        f"<b>OS:</b> <code>{html.escape(platform.platform())}</code>\n"
        f"<b>Python:</b> <code>{platform.python_version()}</code>\n"
        f"<b>CPU cores:</b> <code>{os.cpu_count()}</code>\n"
        f"<b>Load avg:</b> <code>{load_line}</code>\n"
        f"<b>Memory:</b> <code>{mem_line}</code>\n"
        f"<b>Disk:</b> <code>{disk_line}</code>\n"
        f"<b>PID:</b> <code>{os.getpid()}</code>\n"
        f"<b>Uptime:</b> <code>{_human_uptime(time.time() - PANEL_START)}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )


@Client.on_message(filters.command("serverinfo") & OWNER_FILTER)
async def serverinfo_cmd(client: Client, message: Message):
    await message.reply_text(await _server_info_text(), parse_mode=ParseMode.HTML)


# ───────────────────────── /dbstats ─────────────────────────

async def _db_stats_text() -> str:
    await db.ensure_pool()
    if db.db is None:
        return "❌ Database unavailable."

    names = await db.db.list_collection_names()
    names.sort()

    lines = ["📊 <b>DATABASE STATS</b>", "━━━━━━━━━━━━━━━━━━━━━"]
    grand_total = 0

    for name in names:
        try:
            count = await db.db[name].estimated_document_count()
        except Exception:
            count = 0
        grand_total += count
        lines.append(f"• <code>{html.escape(name)}</code> — <b>{count:,}</b>")

    try:
        stats = await db.db.command("dbstats")
        size = _human_bytes(stats.get("dataSize", 0))
        storage = _human_bytes(stats.get("storageSize", 0))
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📦 <b>Documents:</b> {grand_total:,}")
        lines.append(f"💾 <b>Data size:</b> {size}")
        lines.append(f"🗄 <b>Storage:</b> {storage}")
        lines.append(f"📚 <b>Collections:</b> {len(names)}")
    except Exception:
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📦 <b>Total docs:</b> {grand_total:,}")

    return "\n".join(lines)


@Client.on_message(filters.command("dbstats") & OWNER_FILTER)
async def dbstats_cmd(client: Client, message: Message):
    status = await message.reply_text("📊 Gathering stats…")
    try:
        await status.edit_text(await _db_stats_text(), parse_mode=ParseMode.HTML)
    except Exception as e:
        await status.edit_text(f"❌ Error: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("dbcollections") & OWNER_FILTER)
async def dbcollections_cmd(client: Client, message: Message):
    await db.ensure_pool()
    if db.db is None:
        return await message.reply_text("❌ Database unavailable.")
    names = sorted(await db.db.list_collection_names())
    if not names:
        return await message.reply_text("📂 No collections found.")
    text = "📚 <b>COLLECTIONS</b>\n" + "\n".join(f"• <code>{html.escape(n)}</code>" for n in names)
    await message.reply_text(text, parse_mode=ParseMode.HTML)


# ───────────────────────── /dbbackup ─────────────────────────

async def _dump_collection(name: str) -> bytes:
    docs = await db.db[name].find({}).to_list(length=None)
    payload = json.dumps(docs, default=_json_default, ensure_ascii=False, indent=2)
    return payload.encode("utf-8")


async def _send_backup(client: Client, chat_id: int, name: str, status: Message) -> int:
    raw = await _dump_collection(name)
    bio = BytesIO(raw)
    bio.name = f"{name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    count = raw.count(b'"_id"')
    await client.send_document(
        chat_id,
        document=bio,
        caption=(
            f"💾 <b>Backup:</b> <code>{html.escape(name)}</code>\n"
            f"📦 Size: <code>{_human_bytes(len(raw))}</code>\n"
            f"📊 Docs (approx): <code>{count}</code>"
        ),
        parse_mode=ParseMode.HTML,
    )
    return count


@Client.on_message(filters.command("dbbackup") & OWNER_FILTER)
async def dbbackup_cmd(client: Client, message: Message):
    args = message.command
    await db.ensure_pool()
    if db.db is None:
        return await message.reply_text("❌ Database unavailable.")

    if len(args) < 2:
        return await message.reply_text(
            "💾 <b>MongoDB Backup</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/dbbackup all</code> – Back up every collection\n"
            "<code>/dbbackup user_stats</code> – Single collection\n"
            "<code>/dbbackup users games</code> – Multiple collections\n\n"
            "Files are sent here as JSON.",
            parse_mode=ParseMode.HTML,
        )

    target = args[1].lower()
    all_names = sorted(await db.db.list_collection_names())

    if target == "all":
        names = all_names
    else:
        names = args[1:]
        unknown = [n for n in names if n not in all_names]
        if unknown:
            return await message.reply_text(
                "❌ Unknown collections: <code>"
                + ", ".join(html.escape(n) for n in unknown)
                + "</code>",
                parse_mode=ParseMode.HTML,
            )

    status = await message.reply_text(
        f"💾 <b>Backing up {len(names)} collection(s)…</b>",
        parse_mode=ParseMode.HTML,
    )

    done = 0
    failed = []

    for name in names:
        try:
            await _send_backup(client, message.chat.id, name, status)
            done += 1
            try:
                await status.edit_text(
                    f"💾 Backing up… <b>{done}/{len(names)}</b>\n"
                    f"Last: <code>{html.escape(name)}</code>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        except Exception as e:
            failed.append(f"{name}: {str(e)[:60]}")
        await asyncio.sleep(0.3)

    summary = (
        "✅ <b>Backup complete</b>\n"
        f"📚 Collections: <b>{done}/{len(names)}</b>\n"
    )
    if failed:
        summary += "\n⚠️ <b>Failed:</b>\n" + "\n".join(
            f"• <code>{html.escape(f)}</code>" for f in failed[:10]
        )
    await status.edit_text(summary, parse_mode=ParseMode.HTML)


# ───────────────────────── /logs ─────────────────────────

@Client.on_message(filters.command("logs") & OWNER_FILTER)
async def logs_cmd(client: Client, message: Message):
    args = message.command
    n = 100
    if len(args) >= 2 and args[1].isdigit():
        n = max(10, min(int(args[1]), 2000))

    try:
        from utils.logger import get_recent_logs  # type: ignore
        lines = get_recent_logs(n)
        text = "\n".join(lines) if isinstance(lines, list) else str(lines)
    except Exception:
        try:
            from plugins.utilities.logger import get_recent_logs  # type: ignore
            lines = get_recent_logs(n)
            text = "\n".join(lines) if isinstance(lines, list) else str(lines)
        except Exception:
            text = ""

    if not text.strip():
        return await message.reply_text(
            "ℹ️ No in-memory logs available.\n"
            "Open the web dashboard to view live logs.",
            parse_mode=ParseMode.HTML,
        )

    if len(text) > 3500:
        bio = BytesIO(text.encode("utf-8"))
        bio.name = f"logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        await client.send_document(
            message.chat.id,
            document=bio,
            caption=f"📜 Last {n} log lines",
        )
    else:
        await message.reply_text(
            f"<pre>{html.escape(text)}</pre>",
            parse_mode=ParseMode.HTML,
        )


# ───────────────────────── /restart ─────────────────────────

@Client.on_message(filters.command("restart") & OWNER_FILTER)
async def restart_cmd(client: Client, message: Message):
    await message.reply_text(
        "♻️ <b>Restart requested.</b>\nConfirm below.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Confirm restart", callback_data="own:restart_do"),
                    InlineKeyboardButton("❌ Cancel", callback_data="own:close"),
                ]
            ]
        ),
    )


async def _do_restart(client: Client, chat_id: int):
    try:
        await client.send_message(
            chat_id,
            "♻️ <b>Restarting…</b>\nThe bot will be back in a moment.",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    try:
        await client.stop()
    except Exception:
        pass
    try:
        from database.connection import db as _db
        await _db.close()
    except Exception:
        pass
    os.execv(sys.executable, [sys.executable, "bot.py"])


# ───────────────────────── Callback handlers ─────────────────────────

@Client.on_callback_query(filters.regex(r"^own:"))
async def owner_panel_cb(client: Client, cb: CallbackQuery):
    if not cb.from_user or not _is_owner(cb.from_user.id):
        return await cb.answer("Owner only.", show_alert=True)

    action = cb.data.split(":", 1)[1]

    if action == "close":
        try:
            await cb.message.delete()
        except Exception:
            await cb.message.edit_text("✖ Closed.")
        return await cb.answer()

    if action == "uptime":
        await cb.answer()
        return await cb.message.reply_text(
            f"⏱ <b>Uptime:</b> <code>{_human_uptime(time.time() - PANEL_START)}</code>",
            parse_mode=ParseMode.HTML,
        )

    if action == "server":
        await cb.answer("Loading…")
        return await cb.message.reply_text(await _server_info_text(), parse_mode=ParseMode.HTML)

    if action == "dbstats":
        await cb.answer("Loading stats…")
        return await cb.message.reply_text(await _db_stats_text(), parse_mode=ParseMode.HTML)

    if action == "backup_all":
        await cb.answer("Starting backup…")
        await db.ensure_pool()
        if db.db is None:
            return await cb.message.reply_text("❌ Database unavailable.")
        names = sorted(await db.db.list_collection_names())
        status = await cb.message.reply_text(
            f"💾 Backing up <b>{len(names)}</b> collections…",
            parse_mode=ParseMode.HTML,
        )
        done = 0
        failed = []
        for name in names:
            try:
                await _send_backup(client, cb.message.chat.id, name, status)
                done += 1
            except Exception as e:
                failed.append(f"{name}: {str(e)[:60]}")
            await asyncio.sleep(0.3)
        return await status.edit_text(
            f"✅ Backup complete: <b>{done}/{len(names)}</b>"
            + (("\n\n⚠️ Failed:\n" + "\n".join(failed[:10])) if failed else ""),
            parse_mode=ParseMode.HTML,
        )

    if action == "mods":
        await cb.answer()
        try:
            from database.mods import list_mods
            mods = await list_mods()
        except Exception as e:
            return await cb.message.reply_text(f"❌ {html.escape(str(e))}")
        if not mods:
            return await cb.message.reply_text("No mods. Absolute monarchy 👑")
        text = "🧢 <b>MOD TEAM</b>\n" + "\n".join(
            f"• <code>{m['user_id']}</code> — Tier {m['tier']}" for m in mods
        )
        return await cb.message.reply_text(text, parse_mode=ParseMode.HTML)

    if action == "broad":
        await cb.answer()
        return await cb.message.reply_text(
            "📡 <b>Broadcast usage</b>\n\n"
            "<code>/broad -forward</code> – forward (with label)\n"
            "<code>/broad -copy</code> – copy (clean, no label)\n"
            "<code>/broad -users</code> – users only\n"
            "<code>/broad -groups</code> – groups only\n\n"
            "Reply to a message or pass text as argument.",
            parse_mode=ParseMode.HTML,
        )

    if action == "restart_ask":
        await cb.answer()
        return await cb.message.reply_text(
            "♻️ <b>Restart bot?</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Yes", callback_data="own:restart_do"),
                        InlineKeyboardButton("❌ No", callback_data="own:close"),
                    ]
                ]
            ),
        )

    if action == "restart_do":
        await cb.answer("Restarting…", show_alert=False)
        return await _do_restart(client, cb.message.chat.id)

    await cb.answer()
