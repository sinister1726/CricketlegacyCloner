"""
Clone Bot Management — runs in the MAIN bot only.

User commands (DM only):
  /clone <token>   — spawn your clone bot (requires clone premium)
  /rmbot           — stop your running clone bot
  /myclone         — check your clone status

Owner commands:
  /givecp <user_id>   — grant clone premium to a user
  /revokecp <user_id> — revoke clone premium (also kills their bot)
  /clones             — list all active clones with owner, stats & expiry
  /broadall           — broadcast a message through ALL active clone bots
"""

import os
import sys
import asyncio
import subprocess
import httpx

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

    def _is_owner(uid: int) -> bool:
        return uid in Config.OWNER_IDS

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

    def _spawn_clone(user_id: int, token: str) -> subprocess.Popen:
        env = os.environ.copy()
        env["BOT_TOKEN"] = token
        env["IS_CLONE"] = "1"
        env["CLONE_OWNER_ID"] = str(user_id)
        env["MAIN_BOT_USERNAME"] = Config.BOT_USERNAME
        env["MAIN_SUPPORT"] = "https://t.me/clg_fun_zone"
        env["MAIN_SUPPORT_USERNAME"] = "@clg_fun_zone"
        proc = subprocess.Popen(
            [sys.executable, "bot.py"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc

    async def respawn_all_clones():
        """Called on main bot startup — re-spawns any clones that were running."""
        try:
            active = await get_all_active_clones()
            if not active:
                return
            print(f"🧬 Re-spawning {len(active)} clone(s)…")
            for entry in active:
                uid = entry["user_id"]
                token = entry.get("token")
                if not token:
                    continue
                if not await is_clone_premium(uid):
                    await clear_clone_process(uid)
                    continue
                try:
                    proc = _spawn_clone(uid, token)
                    await set_clone_process(uid, token, proc.pid, entry.get("bot_username", ""))
                    print(f"🧬 Re-spawned clone for user {uid} (pid {proc.pid})")
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"⚠️ Failed to re-spawn clone for {uid}: {e}")
        except Exception as e:
            print(f"⚠️ respawn_all_clones error: {e}")

    # ── /clone ────────────────────────────────────────────────────────────────

    @Client.on_message(filters.command("clone") & filters.private)
    async def clone_cmd(client: Client, message: Message):
        user = message.from_user
        args = message.command

        if len(args) < 2:
            return await message.reply_text(
                "🧬 <b>Clone Bot</b>\n\n"
                "Usage: <code>/clone &lt;bot_token&gt;</code>\n\n"
                "Get your bot token from @BotFather.\n\n"
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

        token = args[1].strip()
        status = await message.reply_text("🔍 Validating token…")

        bot_info = await _validate_token(token)
        if not bot_info:
            return await status.edit_text(
                "❌ <b>Invalid or expired bot token.</b>\n\n"
                "Get a fresh token from @BotFather and try again.",
                parse_mode=ParseMode.HTML,
            )

        bot_username = f"@{bot_info.get('username', 'unknown')}"
        bot_name = bot_info.get("first_name", "Bot")

        await status.edit_text(
            f"🚀 Starting <b>{bot_name}</b> ({bot_username})…",
            parse_mode=ParseMode.HTML,
        )

        try:
            proc = _spawn_clone(user.id, token)
        except Exception as e:
            return await status.edit_text(
                f"❌ Failed to start bot: <code>{e}</code>",
                parse_mode=ParseMode.HTML,
            )

        await set_clone_process(user.id, token, proc.pid, bot_username)
        await asyncio.sleep(2)

        await status.edit_text(
            f"✅ <b>Clone Bot Started!</b>\n\n"
            f"🤖 <b>Bot:</b> {bot_name} ({bot_username})\n"
            f"🆔 <b>PID:</b> <code>{proc.pid}</code>\n\n"
            f"💡 DM <b>{bot_username}</b> and send /panel to customise it.\n"
            f"🛑 Use /rmbot here to stop it.\n"
            f"📊 Use /myclone to check status.",
            parse_mode=ParseMode.HTML,
        )

        try:
            await client.send_message(
                Config.LOG_CHANNEL,
                f"🧬 <b>Clone Bot Started</b>\n"
                f"👤 Owner: <a href='tg://user?id={user.id}'>{user.first_name}</a> "
                f"(<code>{user.id}</code>)\n"
                f"🤖 Bot: {bot_username}\n"
                f"🆔 PID: <code>{proc.pid}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    # ── /rmbot ────────────────────────────────────────────────────────────────

    @Client.on_message(filters.command("rmbot") & filters.private)
    async def rmbot_cmd(client: Client, message: Message):
        user = message.from_user
        clone = await get_clone_process(user.id)

        if not clone or not clone.get("running"):
            return await message.reply_text("ℹ️ You don't have a running clone bot.")

        pid = clone.get("pid")
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
            f"You can start a new one anytime with /clone.",
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
        user = message.from_user
        prem = await get_clone_premium(user.id)
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
            exp_str = f"{exp.strftime('%d %b %Y')} ({remaining}d left)"
        else:
            exp_str = "Unknown"

        if clone and clone.get("running"):
            bot_un = clone.get("bot_username", "unknown")
            pid = clone.get("pid", "?")
            started = clone.get("started_at")
            started_str = started.strftime("%d %b %Y  %H:%M UTC") if started else "unknown"
            status_text = (
                f"✅ <b>Bot Running</b>\n"
                f"🤖 {bot_un}\n"
                f"🆔 PID: <code>{pid}</code>\n"
                f"🕐 Started: {started_str}"
            )
            buttons = [[InlineKeyboardButton("🛑 Stop My Bot", callback_data="clone_stop_confirm")]]
        else:
            status_text = "⛔ <b>No bot running</b>\n/clone &lt;token&gt; to start one."
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
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes, Stop It", callback_data="clone_stop_do"),
                    InlineKeyboardButton("❌ Cancel", callback_data="clone_stop_cancel"),
                ]
            ]),
        )

    @Client.on_callback_query(filters.regex("^clone_stop_do$"))
    async def clone_stop_do_cb(client: Client, cb: CallbackQuery):
        await cb.answer()
        user = cb.from_user
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
            "Once paid, your account gets activated within minutes.\n\n"
            "<b>Step 2 — Create Your Bot</b>\n"
            "Open @BotFather on Telegram.\n"
            "Send /newbot → choose a name & username.\n"
            "Copy the bot token.\n\n"
            "<b>Step 3 — Clone It</b>\n"
            "Come back here and send:\n"
            "<code>/clone &lt;paste your token here&gt;</code>\n\n"
            "<b>Step 4 — Customise</b>\n"
            "DM your new bot and send /panel.\n"
            "Set your own start image, message, support group and more — all via buttons.\n\n"
            "<b>Step 5 — Add to Group</b>\n"
            "Add your bot to your tournament group and play! 🏏\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "⏱ Your bot runs for <b>28 days</b> then auto-stops.\n"
            "Renew anytime by contacting @Spideyyye.",
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
                "Usage: <code>/givecp &lt;user_id&gt; [days]</code>\n"
                "Default: 28 days",
                parse_mode=ParseMode.HTML,
            )
        try:
            target = int(args[1])
            days = int(args[2]) if len(args) >= 3 else 28
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
                f"Use <code>/clone &lt;bot_token&gt;</code> in DM to start your clone bot.\n"
                f"Get a token from @BotFather first.\n\n"
                f"Send /clone to see the guide.",
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
            f"✅ Clone premium revoked from <code>{target}</code>.\nTheir bot has been stopped.",
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

    # ── /clones ───────────────────────────────────────────────────────────────

    @Client.on_message(filters.command(["clones", "clonelist"]) & OWNER_FILTER)
    async def clones_cmd(client: Client, message: Message):
        from datetime import datetime
        active = await get_all_active_clones()

        if not active:
            return await message.reply_text(
                "🧬 <b>CLONE BOT STATS</b>\n\n"
                "ℹ️ No active clone bots right now.",
                parse_mode=ParseMode.HTML,
            )

        total = len(active)
        lines = [
            f"🧬 <b>ACTIVE CLONES</b>  •  <b>{total}</b> running\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ]

        for i, entry in enumerate(active, 1):
            uid = entry["user_id"]
            bot_un = entry.get("bot_username", "unknown")
            pid = entry.get("pid", "?")
            started = entry.get("started_at")
            started_str = started.strftime("%d %b %Y") if started else "?"

            prem = await get_clone_premium(uid)
            exp = prem.get("expires_at") if prem else None
            if exp:
                remaining = (exp - datetime.utcnow()).days
                exp_str = f"{exp.strftime('%d %b %Y')} ({remaining}d)"
            else:
                exp_str = "?"

            try:
                user = await client.get_users(uid)
                user_name = f"<a href='tg://user?id={uid}'>{user.first_name}</a>"
            except Exception:
                user_name = f"<code>{uid}</code>"

            lines.append(
                f"\n<b>{i}.</b> 🤖 {bot_un}\n"
                f"   👤 Owner: {user_name} (<code>{uid}</code>)\n"
                f"   🆔 PID: <code>{pid}</code>  •  📅 Since {started_str}\n"
                f"   ⏳ Expires: <b>{exp_str}</b>"
            )

        lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━\n📊 Total: <b>{total}</b> clone(s) running")

        await message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    # ── /broadall ─────────────────────────────────────────────────────────────

    @Client.on_message(filters.command("broadall") & OWNER_FILTER)
    async def broadall_cmd(client: Client, message: Message):
        """Broadcast a message via ALL active clone bots to their owners & groups."""
        if not message.reply_to_message:
            return await message.reply_text(
                "📡 <b>Broadcast via All Clone Bots</b>\n\n"
                "Reply to a message with /broadall to broadcast it through every active clone bot.\n\n"
                "The message will be sent by each clone bot to:\n"
                "• The clone owner's DM\n"
                "• All groups in the shared database",
                parse_mode=ParseMode.HTML,
            )

        active = await get_all_active_clones()
        if not active:
            return await message.reply_text("ℹ️ No active clone bots to broadcast through.")

        status = await message.reply_text(
            f"📡 Broadcasting through <b>{len(active)}</b> clone bot(s)…",
            parse_mode=ParseMode.HTML,
        )

        src_chat = message.reply_to_message.chat.id
        src_msg  = message.reply_to_message.id

        from database.groups import get_all_groups

        success_bots = 0
        fail_bots = 0

        async with httpx.AsyncClient(timeout=20) as http:
            for entry in active:
                token = entry.get("token")
                uid   = entry.get("user_id")
                if not token:
                    fail_bots += 1
                    continue

                bot_success = 0
                bot_fail = 0

                try:
                    await http.post(
                        f"https://api.telegram.org/bot{token}/forwardMessage",
                        json={
                            "chat_id": uid,
                            "from_chat_id": src_chat,
                            "message_id": src_msg,
                        },
                    )
                    bot_success += 1
                except Exception:
                    bot_fail += 1

                try:
                    groups = await get_all_groups()
                    for grp in groups:
                        gid = grp.get("chat_id")
                        if not gid:
                            continue
                        try:
                            await http.post(
                                f"https://api.telegram.org/bot{token}/forwardMessage",
                                json={
                                    "chat_id": gid,
                                    "from_chat_id": src_chat,
                                    "message_id": src_msg,
                                },
                            )
                            bot_success += 1
                        except Exception:
                            bot_fail += 1
                        await asyncio.sleep(0.05)
                except Exception:
                    pass

                if bot_success:
                    success_bots += 1
                else:
                    fail_bots += 1

                await asyncio.sleep(0.5)

        await status.edit_text(
            f"✅ <b>Broadall Complete</b>\n\n"
            f"📡 Bots used: <b>{success_bots}</b> succeeded, <b>{fail_bots}</b> failed\n"
            f"🔢 Total clone bots: <b>{len(active)}</b>",
            parse_mode=ParseMode.HTML,
        )
