"""
Clone Bot Management — runs in the MAIN bot only.

User commands (DM only):
  /clone <token>   — spawn your clone bot (requires clone premium)
  /rmbot           — stop your running clone bot
  /myclone         — check your clone status

Owner commands:
  /givecp <user_id> [days]  — grant clone premium
  /revokecp <user_id>       — revoke clone premium (also kills bot)
  /clones [page]            — paginated list of all clones (5/page),
                              with per-clone user & group counts + grand totals
  /broadall                 — broadcast via ALL active clone bots
  /transferclone @username  — merge a clone's data into main bot DB
"""

import os
import sys
import asyncio
import subprocess
import httpx
import math

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery,
)

from config import Config
from database.clone import (
    is_clone_premium,
    get_clone_premium,
    grant_clone_premium,
    revoke_clone_premium,
    set_clone_process,
    get_clone_process,
    clear_clone_process,
    get_all_active_clones,
)

if Config.IS_CLONE:
    pass
else:
    OWNER_FILTER = filters.user(list(Config.OWNER_IDS))
    _PER_PAGE    = 5

    def _make_db_prefix(bot_username: str) -> str:
        return f"c_{bot_username.replace('@', '').lower()}_"

    async def _validate_token(token: str) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"https://api.telegram.org/bot{token}/getMe")
                data = r.json()
                if data.get("ok"):
                    return data["result"]
        except Exception:
            pass
        return None

    def _spawn_clone(user_id: int, token: str, bot_username: str) -> subprocess.Popen:
        prefix = _make_db_prefix(bot_username)
        env = os.environ.copy()
        env["BOT_TOKEN"]             = token
        env["IS_CLONE"]              = "1"
        env["CLONE_OWNER_ID"]        = str(user_id)
        env["CLONE_DB_PREFIX"]       = prefix
        env["MAIN_BOT_USERNAME"]     = Config.BOT_USERNAME
        env["MAIN_SUPPORT"]          = "https://t.me/clg_fun_zone"
        env["MAIN_SUPPORT_USERNAME"] = "@clg_fun_zone"
        return subprocess.Popen(
            [sys.executable, "bot.py"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    async def respawn_all_clones():
        try:
            active = await get_all_active_clones()
            if not active:
                return
            print(f"🧬 Re-spawning {len(active)} clone(s)…")
            for entry in active:
                uid    = entry["user_id"]
                token  = entry.get("token")
                bot_un = entry.get("bot_username", "")
                if not token:
                    continue
                if not await is_clone_premium(uid):
                    await clear_clone_process(uid)
                    continue
                try:
                    proc   = _spawn_clone(uid, token, bot_un)
                    prefix = _make_db_prefix(bot_un)
                    await set_clone_process(uid, token, proc.pid, bot_un, db_prefix=prefix)
                    print(f"🧬 Re-spawned clone for user {uid} (pid {proc.pid})")
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"⚠️ Failed to re-spawn clone for {uid}: {e}")
        except Exception as e:
            print(f"⚠️ respawn_all_clones error: {e}")

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _count_clone_collections(prefix: str) -> tuple[int, int]:
        """Return (user_count, group_count) for a clone's prefixed collections."""
        from database.connection import db
        uc = gc = 0
        try:
            uc = await db.real_db[f"{prefix}users"].count_documents({})
        except Exception:
            pass
        try:
            gc = await db.real_db[f"{prefix}groups"].count_documents({})
        except Exception:
            pass
        return uc, gc

    async def _build_clones_page(
        client: Client,
        all_clones: list,
        page: int,
    ) -> tuple[str, InlineKeyboardMarkup]:
        from datetime import datetime

        total_clones = len(all_clones)
        total_pages  = max(1, math.ceil(total_clones / _PER_PAGE))
        page         = max(0, min(page, total_pages - 1))

        chunk = all_clones[page * _PER_PAGE : (page + 1) * _PER_PAGE]

        grand_users  = 0
        grand_groups = 0
        lines = [
            f"🧬 <b>ACTIVE CLONES</b>  •  <b>{total_clones}</b> total\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ]

        for i, entry in enumerate(chunk, page * _PER_PAGE + 1):
            uid     = entry["user_id"]
            bot_un  = entry.get("bot_username", "unknown")
            pid     = entry.get("pid", "?")
            prefix  = entry.get("db_prefix") or _make_db_prefix(bot_un)
            started = entry.get("started_at")
            start_str = started.strftime("%d %b %Y") if started else "?"

            prem = await get_clone_premium(uid)
            exp  = prem.get("expires_at") if prem else None
            if exp:
                remaining = (exp - datetime.utcnow()).days
                exp_str   = f"{exp.strftime('%d %b %Y')} ({remaining}d)"
            else:
                exp_str = "?"

            try:
                user      = await client.get_users(uid)
                user_name = f"<a href='tg://user?id={uid}'>{user.first_name}</a>"
            except Exception:
                user_name = f"<code>{uid}</code>"

            uc, gc = await _count_clone_collections(prefix)
            grand_users  += uc
            grand_groups += gc

            lines.append(
                f"\n<b>{i}.</b> 🤖 {bot_un}\n"
                f"   👤 Owner: {user_name} (<code>{uid}</code>)\n"
                f"   👥 Users: <b>{uc:,}</b>  •  🏟 Groups: <b>{gc:,}</b>\n"
                f"   🆔 PID: <code>{pid}</code>  •  📅 Since {start_str}\n"
                f"   ⏳ Expires: <b>{exp_str}</b>"
            )

        # ── grand totals (count ALL clones, not just this page) ───────────────
        all_uc = all_gc = 0
        for entry in all_clones:
            pfx = entry.get("db_prefix") or _make_db_prefix(entry.get("bot_username", ""))
            u, g = await _count_clone_collections(pfx)
            all_uc += u
            all_gc += g

        lines.append(
            f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Grand Total</b>\n"
            f"   🤖 Bots: <b>{total_clones}</b>\n"
            f"   👥 Total Users: <b>{all_uc:,}</b>\n"
            f"   🏟 Total Groups: <b>{all_gc:,}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )

        text = "\n".join(lines)

        # ── pagination buttons ────────────────────────────────────────────────
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"clones_pg_{page - 1}"))
        nav_row.append(
            InlineKeyboardButton(f"📄 {page + 1} / {total_pages}", callback_data="clones_pg_noop")
        )
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"clones_pg_{page + 1}"))

        kb_rows = [nav_row] if total_pages > 1 else []
        kb = InlineKeyboardMarkup(kb_rows) if kb_rows else None

        return text, kb

    # ── /clone ────────────────────────────────────────────────────────────────

    @Client.on_message(filters.command("clone") & filters.private)
    async def clone_cmd(client: Client, message: Message):
        user = message.from_user
        args = message.command

        if len(args) < 2:
            return await message.reply_text(
                "🧬 <b>Clone Bot</b>\n\n"
                "Usage: <code>/clone &lt;bot_token&gt;</code>\n\n"
                "Get your token from @BotFather.\n\n"
                "🔒 Requires <b>Clone Premium</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💎 Get Premium — ₹200/mo", url="https://t.me/Spideyyye"),
                    InlineKeyboardButton("❓ How to Clone?", callback_data="howclone"),
                ]]),
            )

        if not await is_clone_premium(user.id):
            return await message.reply_photo(
                photo="https://graph.org/file/a37d935e98e4c92e04cee-c1871cfafb3f808563.jpg",
                caption=(
                    "🔒 <b>Clone Premium Required</b>\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "Run your own cricket bot for your tournament or group!\n\n"
                    "💰 Price: <b>₹200 / month</b>\n"
                    "⏱ Duration: <b>28 days</b>\n"
                    "🤖 Your own Telegram bot, same game engine\n"
                    "⚙️ Fully customisable via /panel\n"
                    "📊 Completely separate stats & users\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "Contact the owner below to purchase 👇"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Contact Owner — @Spideyyye", url="https://t.me/Spideyyye")],
                    [InlineKeyboardButton("❓ How does it work?", callback_data="howclone")],
                ]),
            )

        existing = await get_clone_process(user.id)
        if existing and existing.get("running"):
            bot_un = existing.get("bot_username", "your bot")
            return await message.reply_text(
                f"⚠️ You already have a running clone: <b>{bot_un}</b>\n\n"
                "Use /rmbot to stop it first, then clone a new bot.",
                parse_mode=ParseMode.HTML,
            )

        token  = args[1].strip()
        status = await message.reply_text("🔍 Validating token…")

        bot_info = await _validate_token(token)
        if not bot_info:
            return await status.edit_text(
                "❌ <b>Invalid or expired bot token.</b>\n\n"
                "Get a fresh token from @BotFather and try again.",
                parse_mode=ParseMode.HTML,
            )

        bot_username = f"@{bot_info.get('username', 'unknown')}"
        bot_name     = bot_info.get("first_name", "Bot")
        db_prefix    = _make_db_prefix(bot_username)

        await status.edit_text(
            f"🚀 Starting <b>{bot_name}</b> ({bot_username})…\n"
            f"📦 Stats prefix: <code>{db_prefix}*</code>",
            parse_mode=ParseMode.HTML,
        )

        try:
            proc = _spawn_clone(user.id, token, bot_username)
        except Exception as e:
            return await status.edit_text(
                f"❌ Failed to start bot: <code>{e}</code>",
                parse_mode=ParseMode.HTML,
            )

        await set_clone_process(user.id, token, proc.pid, bot_username, db_prefix=db_prefix)
        await asyncio.sleep(2)

        await status.edit_text(
            f"✅ <b>Clone Bot Started!</b>\n\n"
            f"🤖 <b>Bot:</b> {bot_name} ({bot_username})\n"
            f"🆔 <b>PID:</b> <code>{proc.pid}</code>\n"
            f"📦 <b>DB prefix:</b> <code>{db_prefix}*</code>\n\n"
            f"💡 DM <b>{bot_username}</b> and send /panel to customise it.\n"
            f"🛑 Use /rmbot here to stop it.\n"
            f"📊 Stats are <b>fully isolated</b> from other bots.",
            parse_mode=ParseMode.HTML,
        )

        try:
            await client.send_message(
                Config.LOG_CHANNEL,
                f"🧬 <b>Clone Bot Started</b>\n"
                f"👤 Owner: <a href='tg://user?id={user.id}'>{user.first_name}</a> "
                f"(<code>{user.id}</code>)\n"
                f"🤖 Bot: {bot_username}\n"
                f"📦 DB prefix: <code>{db_prefix}*</code>\n"
                f"🆔 PID: <code>{proc.pid}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    # ── /rmbot ────────────────────────────────────────────────────────────────

    @Client.on_message(filters.command("rmbot") & filters.private)
    async def rmbot_cmd(client: Client, message: Message):
        user  = message.from_user
        clone = await get_clone_process(user.id)

        if not clone or not clone.get("running"):
            return await message.reply_text("ℹ️ You don't have a running clone bot.")

        pid          = clone.get("pid")
        bot_username = clone.get("bot_username", "your bot")

        if pid:
            try:
                import signal
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass

        await clear_clone_process(user.id)
        await message.reply_text(
            f"✅ <b>Clone bot stopped.</b>\n\n"
            f"🤖 {bot_username} has been shut down.\n"
            f"📊 Your stats are saved and will resume when you restart with /clone.",
            parse_mode=ParseMode.HTML,
        )

        try:
            await client.send_message(
                Config.LOG_CHANNEL,
                f"🛑 <b>Clone Bot Stopped</b>\n"
                f"👤 Owner: <a href='tg://user?id={user.id}'>{user.first_name}</a> "
                f"(<code>{user.id}</code>)\n"
                f"🤖 Bot: {bot_username}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    # ── /myclone ──────────────────────────────────────────────────────────────

    @Client.on_message(filters.command("myclone") & filters.private)
    async def myclone_cmd(client: Client, message: Message):
        user  = message.from_user
        prem  = await get_clone_premium(user.id)
        clone = await get_clone_process(user.id)

        if not prem or not prem.get("active"):
            return await message.reply_text(
                "❌ <b>No Clone Premium</b>\n\n"
                "Contact <b>@Spideyyye</b> — ₹200/month.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💬 Contact @Spideyyye", url="https://t.me/Spideyyye"),
                ]]),
            )

        from datetime import datetime
        exp = prem.get("expires_at")
        if exp:
            remaining = (exp - datetime.utcnow()).days
            exp_str   = f"{exp.strftime('%d %b %Y')} ({remaining}d left)"
        else:
            exp_str = "Unknown"

        if clone and clone.get("running"):
            bot_un    = clone.get("bot_username", "unknown")
            pid       = clone.get("pid", "?")
            prefix    = clone.get("db_prefix", "?")
            started   = clone.get("started_at")
            start_str = started.strftime("%d %b %Y  %H:%M UTC") if started else "unknown"

            uc, gc = await _count_clone_collections(prefix)

            status_text = (
                f"✅ <b>Bot Running</b>\n"
                f"🤖 {bot_un}\n"
                f"🆔 PID: <code>{pid}</code>  •  📦 DB: <code>{prefix}*</code>\n"
                f"👥 Users: <b>{uc:,}</b>  •  🏟 Groups: <b>{gc:,}</b>\n"
                f"🕐 Started: {start_str}"
            )
            buttons = [[InlineKeyboardButton("🛑 Stop My Bot", callback_data="clone_stop_confirm")]]
        else:
            status_text = "⛔ <b>No bot running</b>\nSend /clone &lt;token&gt; to start one."
            buttons = []

        await message.reply_text(
            f"🧬 <b>MY CLONE STATUS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 Premium: <b>Active</b>\n"
            f"⏳ Expires: {exp_str}\n\n"
            f"{status_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
        )

    @Client.on_callback_query(filters.regex("^clone_stop_confirm$"))
    async def clone_stop_confirm_cb(client: Client, cb: CallbackQuery):
        await cb.answer()
        await cb.message.reply_text(
            "⚠️ Are you sure you want to stop your clone bot?",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Yes, Stop It", callback_data="clone_stop_do"),
                InlineKeyboardButton("❌ Cancel",       callback_data="clone_stop_cancel"),
            ]]),
        )

    @Client.on_callback_query(filters.regex("^clone_stop_do$"))
    async def clone_stop_do_cb(client: Client, cb: CallbackQuery):
        await cb.answer()
        user  = cb.from_user
        clone = await get_clone_process(user.id)
        if clone and clone.get("pid"):
            try:
                import signal
                os.kill(clone["pid"], signal.SIGTERM)
            except Exception:
                pass
        await clear_clone_process(user.id)
        try:
            await cb.message.edit_text("✅ Clone bot stopped successfully.")
        except Exception:
            pass

    @Client.on_callback_query(filters.regex("^clone_stop_cancel$"))
    async def clone_stop_cancel_cb(client: Client, cb: CallbackQuery):
        await cb.answer("Cancelled.")
        try:
            await cb.message.delete()
        except Exception:
            pass

    # ── "How to Clone?" callback ──────────────────────────────────────────────

    @Client.on_callback_query(filters.regex("^howclone$"))
    async def howclone_cb(client: Client, cb: CallbackQuery):
        await cb.answer()
        await cb.message.reply_text(
            "❓ <b>HOW TO GET YOUR CLONE BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Step 1 — Buy Premium</b>\n"
            "Contact @Spideyyye and pay ₹200/month.\n"
            "Activated within minutes after payment.\n\n"
            "<b>Step 2 — Create Your Bot</b>\n"
            "Open @BotFather → /newbot → pick a name & username.\n"
            "Copy the bot token.\n\n"
            "<b>Step 3 — Clone It</b>\n"
            "Come back here and send:\n"
            "<code>/clone &lt;your bot token here&gt;</code>\n\n"
            "<b>Step 4 — Customise</b>\n"
            "DM your new bot → /panel → set start image, message,\n"
            "support group and more — all via buttons.\n\n"
            "<b>Step 5 — Add to Group</b>\n"
            "Add your bot to your tournament group and play! 🏏\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ Stats are <b>100% separate</b> from all other bots.\n"
            "♻️ Restart anytime — stats recover from the same token!\n"
            "⏱ Runs for <b>28 days</b> then auto-stops.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 Contact @Spideyyye", url="https://t.me/Spideyyye"),
            ]]),
        )

    # ── /givecp ───────────────────────────────────────────────────────────────

    @Client.on_message(filters.command("givecp") & OWNER_FILTER)
    async def givecp_cmd(client: Client, message: Message):
        args = message.command
        if len(args) < 2:
            return await message.reply_text(
                "Usage: <code>/givecp &lt;user_id&gt; [days]</code>\nDefault: 28 days",
                parse_mode=ParseMode.HTML,
            )
        try:
            target = int(args[1])
            days   = int(args[2]) if len(args) >= 3 else 28
        except ValueError:
            return await message.reply_text("❌ Invalid user ID or days.")

        await grant_clone_premium(target, message.from_user.id, days=days)

        from datetime import datetime, timedelta
        exp = (datetime.utcnow() + timedelta(days=days)).strftime("%d %b %Y")

        await message.reply_text(
            f"✅ <b>Clone Premium Granted</b>\n\n"
            f"👤 User: <code>{target}</code>\n"
            f"⏳ Duration: <b>{days} days</b>\n"
            f"📅 Expires: <b>{exp}</b>",
            parse_mode=ParseMode.HTML,
        )

        try:
            await client.send_message(
                target,
                f"🎉 <b>Clone Premium Activated!</b>\n\n"
                f"You now have Clone Premium for <b>{days} days</b>.\n"
                f"📅 Expires: <b>{exp}</b>\n\n"
                f"Use <code>/clone &lt;bot_token&gt;</code> in DM to start your bot.\n"
                f"Get a token from @BotFather first.\n\n"
                f"📊 Your bot has <b>completely separate stats</b> from all other bots.\n"
                f"♻️ Stats are saved — restarting the same bot preserves everything.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    # ── /revokecp ─────────────────────────────────────────────────────────────

    @Client.on_message(filters.command("revokecp") & OWNER_FILTER)
    async def revokecp_cmd(client: Client, message: Message):
        args = message.command
        if len(args) < 2:
            return await message.reply_text(
                "Usage: <code>/revokecp &lt;user_id&gt;</code>",
                parse_mode=ParseMode.HTML,
            )
        try:
            target = int(args[1])
        except ValueError:
            return await message.reply_text("❌ Invalid user ID.")

        await revoke_clone_premium(target)
        await message.reply_text(
            f"✅ Clone premium revoked from <code>{target}</code>. Their bot has been stopped.",
            parse_mode=ParseMode.HTML,
        )
        try:
            await client.send_message(
                target,
                "⛔ <b>Clone Premium Revoked</b>\n\nYour clone bot has been stopped by the owner.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    # ── /clones (paginated) ───────────────────────────────────────────────────

    @Client.on_message(filters.command(["clones", "clonelist"]) & OWNER_FILTER)
    async def clones_cmd(client: Client, message: Message):
        active = await get_all_active_clones()
        if not active:
            return await message.reply_text(
                "🧬 <b>CLONE BOT STATS</b>\n\nℹ️ No active clone bots right now.",
                parse_mode=ParseMode.HTML,
            )

        args = message.command
        try:
            page = int(args[1]) - 1
        except (IndexError, ValueError):
            page = 0

        wait = await message.reply_text("⏳ Fetching clone stats…")
        text, kb = await _build_clones_page(client, active, page)
        try:
            await wait.delete()
        except Exception:
            pass
        await message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=kb,
        )

    @Client.on_callback_query(filters.regex(r"^clones_pg_(\d+)$") & OWNER_FILTER)
    async def clones_page_cb(client: Client, cb: CallbackQuery):
        page   = int(cb.data.split("_")[-1])
        active = await get_all_active_clones()
        if not active:
            return await cb.answer("No active clones.", show_alert=True)

        await cb.answer("Loading…")
        text, kb = await _build_clones_page(client, active, page)
        try:
            await cb.message.edit_text(
                text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=kb,
            )
        except Exception:
            pass

    @Client.on_callback_query(filters.regex(r"^clones_pg_noop$") & OWNER_FILTER)
    async def clones_noop_cb(client: Client, cb: CallbackQuery):
        await cb.answer("You're already viewing this page.")

    # ── /broadall ─────────────────────────────────────────────────────────────

    @Client.on_message(filters.command("broadall") & OWNER_FILTER)
    async def broadall_cmd(client: Client, message: Message):
        if not message.reply_to_message:
            return await message.reply_text(
                "📡 <b>Broadcast via All Clone Bots</b>\n\n"
                "Reply to a message with /broadall to send it through every active clone bot\n"
                "→ clone owner DMs + all groups in DB.",
                parse_mode=ParseMode.HTML,
            )

        active = await get_all_active_clones()
        if not active:
            return await message.reply_text("ℹ️ No active clone bots to broadcast through.")

        status   = await message.reply_text(
            f"📡 Broadcasting through <b>{len(active)}</b> clone bot(s)…",
            parse_mode=ParseMode.HTML,
        )
        src_chat = message.reply_to_message.chat.id
        src_msg  = message.reply_to_message.id

        from database.groups import get_all_groups

        success_bots = 0
        fail_bots    = 0

        async with httpx.AsyncClient(timeout=20) as http:
            for entry in active:
                token = entry.get("token")
                uid   = entry.get("user_id")
                if not token:
                    fail_bots += 1
                    continue

                ok = False
                try:
                    await http.post(
                        f"https://api.telegram.org/bot{token}/forwardMessage",
                        json={"chat_id": uid, "from_chat_id": src_chat, "message_id": src_msg},
                    )
                    ok = True
                except Exception:
                    pass

                try:
                    groups = await get_all_groups()
                    for grp in groups:
                        gid = grp.get("chat_id")
                        if not gid:
                            continue
                        try:
                            await http.post(
                                f"https://api.telegram.org/bot{token}/forwardMessage",
                                json={"chat_id": gid, "from_chat_id": src_chat, "message_id": src_msg},
                            )
                        except Exception:
                            pass
                        await asyncio.sleep(0.05)
                except Exception:
                    pass

                success_bots += 1 if ok else 0
                if not ok:
                    fail_bots += 1
                await asyncio.sleep(0.5)

        await status.edit_text(
            f"✅ <b>Broadall Complete</b>\n\n"
            f"📡 Bots succeeded: <b>{success_bots}</b> / {len(active)}\n"
            f"❌ Failed: <b>{fail_bots}</b>",
            parse_mode=ParseMode.HTML,
        )

    # ── /transferclone ────────────────────────────────────────────────────────

    @Client.on_message(filters.command("transferclone") & OWNER_FILTER)
    async def transferclone_cmd(client: Client, message: Message):
        args = message.command
        if len(args) < 2:
            return await message.reply_text(
                "📦 <b>Transfer Clone Data → Main Bot</b>\n\n"
                "Usage: <code>/transferclone @botusername</code>\n\n"
                "Merges users and stats from the clone into the main bot DB.\n"
                "Existing user stats are <b>added</b> (not overwritten).",
                parse_mode=ParseMode.HTML,
            )

        from database.connection import db

        target_raw  = args[1].lstrip("@").lower()
        clone_entry = await db.db["user_clones"].find_one(
            {"bot_username": {"$regex": f"^@?{target_raw}$", "$options": "i"}}
        )

        if not clone_entry:
            return await message.reply_text(
                f"❌ No clone record found for @{target_raw}.\n\n"
                f"Use /clones to see all known clone bots.",
                parse_mode=ParseMode.HTML,
            )

        prefix    = clone_entry.get("db_prefix") or _make_db_prefix(
            clone_entry.get("bot_username", target_raw)
        )
        owner_uid = clone_entry.get("user_id", "?")
        status    = await message.reply_text(
            f"🔄 Transferring from <code>{prefix}*</code>…",
            parse_mode=ParseMode.HTML,
        )

        real_db      = db.real_db
        users_added  = 0
        stats_merged = 0
        groups_added = 0

        try:
            clone_users = await real_db[f"{prefix}users"].find({}).to_list(length=None)
            for u in clone_users:
                u.pop("_id", None)
                if not await real_db["users"].find_one({"user_id": u["user_id"]}):
                    await real_db["users"].insert_one(u)
                    users_added += 1
        except Exception as e:
            print(f"transferclone users error: {e}")

        try:
            clone_stats = await real_db[f"{prefix}user_stats"].find({}).to_list(length=None)
            for s in clone_stats:
                s.pop("_id", None)
                uid_s = s.get("user_id")
                if not uid_s:
                    continue
                existing = await real_db["user_stats"].find_one({"user_id": uid_s})
                if not existing:
                    await real_db["user_stats"].insert_one(s)
                else:
                    await real_db["user_stats"].update_one(
                        {"user_id": uid_s},
                        {"$inc": {
                            "runs":      s.get("runs", 0),
                            "wickets":   s.get("wickets", 0),
                            "matches":   s.get("matches", 0),
                            "fifties":   s.get("fifties", 0),
                            "centuries": s.get("centuries", 0),
                            "sixes":     s.get("sixes", 0),
                            "fours":     s.get("fours", 0),
                            "wins":      s.get("wins", 0),
                            "losses":    s.get("losses", 0),
                        }},
                    )
                stats_merged += 1
        except Exception as e:
            print(f"transferclone stats error: {e}")

        try:
            clone_groups = await real_db[f"{prefix}groups"].find({}).to_list(length=None)
            for g in clone_groups:
                g.pop("_id", None)
                if not await real_db["groups"].find_one({"chat_id": g["chat_id"]}):
                    await real_db["groups"].insert_one(g)
                    groups_added += 1
        except Exception as e:
            print(f"transferclone groups error: {e}")

        await status.edit_text(
            f"✅ <b>Transfer Complete</b>\n\n"
            f"📦 Source: @{target_raw}  (prefix <code>{prefix}*</code>)\n"
            f"👤 Clone owner: <code>{owner_uid}</code>\n\n"
            f"👥 New users added: <b>{users_added}</b>\n"
            f"📊 Stats merged: <b>{stats_merged}</b>\n"
            f"🏟 Groups added: <b>{groups_added}</b>",
            parse_mode=ParseMode.HTML,
        )
