"""
Clone Bot Management — runs in the MAIN bot only.

User commands (DM only):
  /clone <token>   — spawn your clone bot (requires clone premium)
  /rmbot           — stop your running clone bot
  /myclone         — check your clone status

Owner commands:
  /givecp <user_id>   — grant clone premium to a user
  /revokecp <user_id> — revoke clone premium (also kills their bot)
  /clonelist          — list all active clones
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

    @Client.on_message(filters.command("clone") & filters.private)
    async def clone_cmd(client: Client, message: Message):
        user = message.from_user
        args = message.command

        if len(args) < 2:
            return await message.reply_text(
                "🧬 <b>Clone Bot</b>\n\n"
                "Usage: <code>/clone &lt;bot_token&gt;</code>\n\n"
                "Get your bot token from @BotFather.\n"
                "Requires <b>Clone Premium</b> — contact @Spideyyye (₹200/month).",
                parse_mode=ParseMode.HTML,
            )

        token = args[1].strip()

        if not await is_clone_premium(user.id):
            return await message.reply_text(
                "🔒 <b>Clone Premium Required</b>\n\n"
                "You need Clone Premium to use this feature.\n\n"
                "💬 Contact <b>@Spideyyye</b> to purchase\n"
                "💰 Price: <b>₹200/month</b>\n"
                "⏱ Duration: <b>28 days</b>",
                parse_mode=ParseMode.HTML,
            )

        existing = await get_clone_process(user.id)
        if existing and existing.get("running"):
            bot_un = existing.get("bot_username", "your bot")
            return await message.reply_text(
                f"⚠️ You already have a running clone: <b>{bot_un}</b>\n\n"
                "Use /rmbot to stop it before cloning a new bot.",
                parse_mode=ParseMode.HTML,
            )

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

        await status.edit_text(f"🚀 Starting <b>{bot_name}</b> ({bot_username})…", parse_mode=ParseMode.HTML)

        try:
            proc = _spawn_clone(user.id, token)
        except Exception as e:
            return await status.edit_text(f"❌ Failed to start bot: <code>{e}</code>", parse_mode=ParseMode.HTML)

        await set_clone_process(user.id, token, proc.pid, bot_username)

        await asyncio.sleep(2)

        await status.edit_text(
            f"✅ <b>Clone Bot Started!</b>\n\n"
            f"🤖 <b>Bot:</b> {bot_name} ({bot_username})\n"
            f"🆔 <b>PID:</b> <code>{proc.pid}</code>\n\n"
            f"💡 Send /panel to <b>{bot_username}</b> in DM to customise it.\n"
            f"🛑 Use /rmbot here to stop it.",
            parse_mode=ParseMode.HTML,
        )

        try:
            await client.send_message(
                Config.LOG_CHANNEL,
                f"🧬 <b>Clone Bot Started</b>\n"
                f"👤 Owner: <a href='tg://user?id={user.id}'>{user.first_name}</a> (<code>{user.id}</code>)\n"
                f"🤖 Bot: {bot_username}\n"
                f"🆔 PID: <code>{proc.pid}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

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
            f"🤖 {bot_username} has been shut down.\n\n"
            f"You can start a new one anytime with /clone <token>.",
            parse_mode=ParseMode.HTML,
        )

        try:
            await client.send_message(
                Config.LOG_CHANNEL,
                f"🛑 <b>Clone Bot Stopped</b>\n"
                f"👤 Owner: <a href='tg://user?id={user.id}'>{user.first_name}</a> (<code>{user.id}</code>)\n"
                f"🤖 Bot: {bot_username}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    @Client.on_message(filters.command("myclone") & filters.private)
    async def myclone_cmd(client: Client, message: Message):
        user = message.from_user
        prem = await get_clone_premium(user.id)
        clone = await get_clone_process(user.id)

        if not prem or not prem.get("active"):
            return await message.reply_text(
                "❌ <b>No Clone Premium</b>\n\n"
                "You don't have an active clone premium.\n"
                "Contact <b>@Spideyyye</b> — ₹200/month.",
                parse_mode=ParseMode.HTML,
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
            started_str = started.strftime("%d %b %Y %H:%M") if started else "unknown"
            status_text = (
                f"✅ <b>Running</b>\n"
                f"🤖 Bot: <b>{bot_un}</b>\n"
                f"🆔 PID: <code>{pid}</code>\n"
                f"🕐 Started: {started_str}"
            )
        else:
            status_text = "⛔ <b>No bot running</b>\nUse /clone <token> to start one."

        await message.reply_text(
            f"🧬 <b>MY CLONE STATUS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 Premium: <b>Active</b>\n"
            f"⏳ Expires: {exp_str}\n\n"
            f"{status_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━",
            parse_mode=ParseMode.HTML,
        )

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
                f"Use /clone &lt;bot_token&gt; in DM to start your clone bot.\n"
                f"Get a bot token from @BotFather.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    @Client.on_message(filters.command("revokecp") & OWNER_FILTER)
    async def revokecp_cmd(client: Client, message: Message):
        args = message.command
        if len(args) < 2:
            return await message.reply_text("Usage: <code>/revokecp &lt;user_id&gt;</code>", parse_mode=ParseMode.HTML)
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

    @Client.on_message(filters.command("clonelist") & OWNER_FILTER)
    async def clonelist_cmd(client: Client, message: Message):
        active = await get_all_active_clones()
        if not active:
            return await message.reply_text("ℹ️ No active clone bots right now.")

        lines = [f"🧬 <b>ACTIVE CLONES ({len(active)})</b>\n━━━━━━━━━━━━━━━━━━━━━"]
        for entry in active:
            uid = entry["user_id"]
            bot_un = entry.get("bot_username", "unknown")
            pid = entry.get("pid", "?")
            started = entry.get("started_at")
            started_str = started.strftime("%d %b") if started else "?"
            prem = await get_clone_premium(uid)
            exp = prem.get("expires_at") if prem else None
            exp_str = exp.strftime("%d %b %Y") if exp else "?"
            lines.append(
                f"🤖 {bot_un}\n"
                f"   👤 <code>{uid}</code> | PID <code>{pid}</code>\n"
                f"   🕐 Started {started_str} | ⏳ Expires {exp_str}"
            )

        await message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML)
