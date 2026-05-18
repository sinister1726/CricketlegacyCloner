"""
/settings — per-group feature toggle panel (admins only).

Free    : super_over, ai_summary, achievement_alerts, auto_play_again, team_names, auto_pin_members
Premium : spam_free (Silver+), disabled_numbers (Gold+), edge_rule (Gold+),
          ball_timeout (Silver+), over_limit (Silver+)

Callback scheme:
  gs_home                       main panel
  gs_view_<feature>             feature sub-panel
  gs_toggle_<feature>_<1|0>     toggle ON/OFF
  gs_dn                         disabled-numbers panel
  gs_dn_toggle_<n>              toggle number n (0-6)
  gs_timeout                    timeout picker panel
  gs_timeout_set_<secs>         set timeout to <secs>
  gs_ol                         over-limit picker panel
  gs_ol_set_<n>                 set over limit to <n>
"""

import html as _html

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
)
from pyrogram.enums import ParseMode

from database.group_settings import get_group_settings, set_group_setting, get_setting
from database.premium import get_premium, PLANS, plan_unlocked
from utils.guards import is_group_admin


FREE_FEATURES = [
    ("super_over",         "⚡ Super Over"),
    ("ai_summary",         "🧠 AI Summary"),
    ("achievement_alerts", "🔔 Achievements"),
    ("auto_play_again",    "🔄 Play Again"),
    ("team_names",         "🏷 Team Names"),
    ("auto_pin_members",   "📌 Auto-Pin List"),
]

PREMIUM_FEATURES = [
    ("spam_free",        "🛡 Spam Free",      "silver"),
    ("disabled_numbers", "🔲 Dis. Numbers",   "gold"),
    ("edge_rule",        "⚠️ Edge Rule",       "gold"),
    ("over_limit",       "🎳 Over Limit",      "silver"),
]

TIMEOUT_OPTIONS = [
    (30,  "30s"),
    (60,  "1m"),
    (120, "2m"),
    (150, "2m 30s"),
    (180, "3m"),
    (300, "5m"),
]

OVER_LIMIT_OPTIONS = [1, 2, 3, 4, 5]

FEATURE_DESC = {
    "super_over": (
        "⚡ <b>Super Over</b>  🚧 <i>Coming Soon</i>\n\n"
        "When a match ends in a tie, a Super Over kicks off.\n"
        "Each team bats 1 over with 1 wicket — highest score wins!\n\n"
        "🔧 This feature is still being built.\n"
        "It will be available soon — try other features for now!"
    ),
    "ai_summary": (
        "🧠 <b>AI Over Summary</b>\n\n"
        "After every over our AI commentator delivers a sharp,\n"
        "funny 2–3 line analysis of what just happened.\n"
        "Powered by Llama 3.1 70B via NVIDIA API.\n\n"
        "🆓 <b>Free feature — default on.</b>"
    ),
    "achievement_alerts": (
        "🔔 <b>Achievement Alerts</b>\n\n"
        "Real-time announcements in the group for:\n"
        "50s, 100s, 150s, 250s, 3-wicket hauls, 5-fors,\n"
        "hat-tricks, ducks, and partnership milestones.\n\n"
        "🆓 <b>Free feature — default on.</b>"
    ),
    "auto_play_again": (
        "🔄 <b>Auto Play Again</b>\n\n"
        "After every match a 'Play Again?' prompt appears\n"
        "in the group so players can quickly start a new game.\n\n"
        "🆓 <b>Free feature — default on.</b>"
    ),
    "team_names": (
        "🏷 <b>Custom Team Names</b>\n\n"
        "After captains are assigned, both are DM'd by the bot\n"
        "and have <b>45 seconds</b> to choose a name for their team.\n\n"
        "Examples: Royal Nexors, Thunder Kings, Desert Strikers…\n\n"
        "Names appear in the match overview, result message,\n"
        "and everywhere Team A/B is normally shown.\n\n"
        "🆓 <b>Free feature — default off.</b>"
    ),
    "spam_free": (
        "🛡 <b>Spam Free Mode</b>  <i>(Premium)</i>\n\n"
        "Prevents bowlers from sending the same number\n"
        "3 consecutive times in a row.\n\n"
        "Example: 4 → 4 → 4 is blocked. 4 → 4 → 5 is fine.\n\n"
        "📦 Requires <b>🥈 Silver plan</b> or above."
    ),
    "disabled_numbers": (
        "🔲 <b>Disabled Numbers</b>  <i>(Premium)</i>\n\n"
        "Block up to 2 numbers (0–6) from the game entirely.\n"
        "Neither batters nor bowlers can use them.\n\n"
        "Great for custom game modes and tighter strategies.\n\n"
        "📦 Requires <b>🥇 Gold plan</b>."
    ),
    "edge_rule": (
        "⚠️ <b>Edge Rule</b>  <i>(Premium)</i>\n\n"
        "Batter plays 3 consecutive 0s → warning DM sent.\n"
        "4th consecutive 0 → automatically out!\n\n"
        "Encourages active batting and punishes pure defence.\n\n"
        "📦 Requires <b>🥇 Gold plan</b>."
    ),
    "ball_timeout": (
        "⏱ <b>Ball Timeout</b>  <i>(Premium)</i>\n\n"
        "Set how long a player has to respond each ball.\n"
        "Default: <b>1 minute</b>.\n\n"
        "Options: 30s · 1m · 2m · 2m 30s · 3m · 5m\n\n"
        "After the timer → warning, then -6 runs penalty.\n\n"
        "📦 Requires <b>🥈 Silver plan</b> or above."
    ),
    "over_limit": (
        "🎳 <b>Per-Bowler Over Limit</b>  <i>(Premium)</i>\n\n"
        "Limit how many overs a single bowler can bowl per innings.\n\n"
        "Options: 1, 2, 3, 4, or 5 overs max.\n"
        "If a bowler hits their limit the captain must pick a new one.\n\n"
        "Forces captains to rotate their attack — more strategy!\n\n"
        "📦 Requires <b>🥈 Silver plan</b> or above."
    ),
    "auto_pin_members": (
        "📌 <b>Auto-Pin Members List</b>\n\n"
        "When /members or /teams is used with captains set,\n"
        "the members list card gets automatically pinned in the group.\n\n"
        "Keeps the squad info visible at the top for everyone.\n\n"
        "🆓 <b>Free feature — default on.</b>"
    ),
}

PLAN_LOCK_MSG = {
    "silver": "🔒 Unlock with <b>🥈 Silver Plan</b> (₹30/month).",
    "gold":   "🔒 Unlock with <b>🥇 Gold Plan</b> (₹80/month).",
    "basic":  "🔒 Unlock with <b>🥈 Silver Plan</b> (₹30/month).",
}


def _timeout_label(secs: int) -> str:
    for s, lbl in TIMEOUT_OPTIONS:
        if s == secs:
            return lbl
    m, rem = divmod(secs, 60)
    return f"{m}m{rem:02d}s" if rem else f"{m}m"


# ─── Panel builders ───────────────────────────────────────────────────────────

async def _main_panel(chat_id: int):
    settings  = await get_group_settings(chat_id)
    premium   = await get_premium(chat_id)
    plan_name = PLANS.get(premium["plan"], {}).get("name", premium["plan"].title()) if premium else None

    plan_line = (
        f"✨ <b>Plan:</b> {plan_name}"
        if plan_name else
        "🔓 <b>Free tier</b>  —  contact owner for premium"
    )
    text = (
        "⚙️ <b>GROUP SETTINGS</b>\n"
        f"{plan_line}\n\n"
        "🆓 <b>Free Features</b>"
    )

    buttons = []

    # Free features — 2 per row
    free_pairs = [FREE_FEATURES[i:i+2] for i in range(0, len(FREE_FEATURES), 2)]
    for pair in free_pairs:
        row = []
        for key, label in pair:
            val    = settings.get(key, True)
            status = "✅" if val else "❌"
            row.append(InlineKeyboardButton(f"{status} {label}", callback_data=f"gs_view_{key}"))
        buttons.append(row)

    buttons.append([InlineKeyboardButton("─── 💎 Premium ───", callback_data="gs_noop")])

    spam_unlocked = premium and plan_unlocked(premium, "silver")
    dn_unlocked   = premium and plan_unlocked(premium, "gold")
    edge_unlocked = premium and plan_unlocked(premium, "gold")
    to_unlocked   = premium and plan_unlocked(premium, "silver")
    ol_unlocked   = premium and plan_unlocked(premium, "silver")

    # Row: spam_free | disabled_numbers
    spam_status = ("✅" if settings.get("spam_free", False) else "❌") if spam_unlocked else "🔒"
    dn          = settings.get("disabled_numbers", [])
    dn_str      = f"[{', '.join(map(str, dn))}]" if dn else "[none]"
    dn_status   = f"🔲 {dn_str}" if dn_unlocked else "🔒"
    buttons.append([
        InlineKeyboardButton(f"{spam_status} 🛡 Spam Free",   callback_data="gs_view_spam_free"),
        InlineKeyboardButton(f"{dn_status} Numbers",          callback_data="gs_dn"),
    ])

    # Row: edge_rule | ball_timeout
    edge_status = ("✅" if settings.get("edge_rule", False) else "❌") if edge_unlocked else "🔒"
    cur_timeout = settings.get("ball_timeout", 60)
    to_label    = _timeout_label(cur_timeout)
    to_status   = f"⏱ {to_label}" if to_unlocked else "🔒 ⏱ Timeout"
    buttons.append([
        InlineKeyboardButton(f"{edge_status} ⚠️ Edge Rule", callback_data="gs_view_edge_rule"),
        InlineKeyboardButton(f"{to_status}",                callback_data="gs_timeout"),
    ])

    # Row: over_limit (standalone)
    ol_val     = settings.get("over_limit", 0)
    ol_display = f"{ol_val}ov" if ol_val and ol_unlocked else ("🔒" if not ol_unlocked else "off")
    buttons.append([
        InlineKeyboardButton(f"🎳 Over Limit: {ol_display}", callback_data="gs_ol"),
    ])

    buttons.append([InlineKeyboardButton("💎 How to get Premium?", callback_data="gs_premium_help")])
    buttons.append([InlineKeyboardButton("✖ Close", callback_data="gs_close")])

    return text, InlineKeyboardMarkup(buttons)


async def _feature_panel(chat_id: int, feature: str):
    settings        = await get_group_settings(chat_id)
    premium         = await get_premium(chat_id)
    prem_keys       = {f[0] for f in PREMIUM_FEATURES} | {"ball_timeout"}
    is_prem_feature = feature in prem_keys
    req_plan        = next(
        (f[2] for f in PREMIUM_FEATURES if f[0] == feature),
        "basic" if feature == "ball_timeout" else None,
    )
    has_access = not is_prem_feature or (premium and plan_unlocked(premium, req_plan))
    desc       = FEATURE_DESC.get(feature, f"⚙️ <b>{feature}</b>")

    if feature == "super_over":
        return desc, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="gs_home")]])

    if not has_access:
        lock_msg = PLAN_LOCK_MSG.get(req_plan, "🔒 Upgrade to unlock.")
        text = f"{desc}\n\n{lock_msg}"
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="gs_home")]])

    default = False if is_prem_feature else True
    val     = settings.get(feature, default)
    status  = "✅ <b>ON</b>" if val else "❌ <b>OFF</b>"
    text    = f"{desc}\n\nStatus: {status}"
    buttons = [
        [
            InlineKeyboardButton("✅ Enable",  callback_data=f"gs_toggle_{feature}_1"),
            InlineKeyboardButton("❌ Disable", callback_data=f"gs_toggle_{feature}_0"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="gs_home")],
    ]
    return text, InlineKeyboardMarkup(buttons)


async def _dn_panel(chat_id: int):
    settings = await get_group_settings(chat_id)
    premium  = await get_premium(chat_id)
    dn       = settings.get("disabled_numbers", [])

    if not premium or not plan_unlocked(premium, "gold"):
        text = (
            f"{FEATURE_DESC['disabled_numbers']}\n\n"
            f"{PLAN_LOCK_MSG['gold']}"
        )
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="gs_home")]])

    text = (
        "🔲 <b>Disabled Numbers</b>\n"
        "Tap a number to toggle it on/off. Max 2 blocked.\n\n"
        f"🚫 Blocked: <b>{', '.join(map(str, dn)) if dn else 'None'}</b>"
    )
    num_row = [
        InlineKeyboardButton(
            f"🚫 {n}" if n in dn else str(n),
            callback_data=f"gs_dn_toggle_{n}",
        )
        for n in range(7)
    ]
    buttons = [num_row, [InlineKeyboardButton("🔙 Back", callback_data="gs_home")]]
    return text, InlineKeyboardMarkup(buttons)


async def _timeout_panel(chat_id: int):
    premium     = await get_premium(chat_id)
    cur_timeout = await get_setting(chat_id, "ball_timeout") or 60
    unlocked    = premium and plan_unlocked(premium, "silver")

    if not unlocked:
        text = (
            f"{FEATURE_DESC['ball_timeout']}\n\n"
            f"{PLAN_LOCK_MSG['silver']}"
        )
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="gs_home")]])

    text = (
        "⏱ <b>Ball Timeout</b>\n"
        "Set how long each player has to respond.\n"
        "After timeout → warning → -6 run penalty.\n\n"
        f"🕐 <b>Current:</b> {_timeout_label(cur_timeout)}"
    )

    rows = []
    pairs = [TIMEOUT_OPTIONS[i:i+2] for i in range(0, len(TIMEOUT_OPTIONS), 2)]
    for pair in pairs:
        row = []
        for secs, label in pair:
            mark = "✅ " if secs == cur_timeout else ""
            row.append(InlineKeyboardButton(f"{mark}{label}", callback_data=f"gs_timeout_set_{secs}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="gs_home")])

    return text, InlineKeyboardMarkup(rows)


async def _over_limit_panel(chat_id: int):
    premium  = await get_premium(chat_id)
    cur_ol   = await get_setting(chat_id, "over_limit") or 0
    unlocked = premium and plan_unlocked(premium, "silver")

    if not unlocked:
        text = (
            f"{FEATURE_DESC['over_limit']}\n\n"
            f"{PLAN_LOCK_MSG['silver']}"
        )
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="gs_home")]])

    cur_label = f"{cur_ol} over(s) max" if cur_ol else "Off (no limit)"
    text = (
        "🎳 <b>Per-Bowler Over Limit</b>\n"
        "Tap to set the max overs one bowler can bowl.\n"
        "Set to <b>Off</b> to disable.\n\n"
        f"🕐 <b>Current:</b> {cur_label}"
    )

    opt_row = []
    for n in OVER_LIMIT_OPTIONS:
        mark = "✅ " if n == cur_ol else ""
        opt_row.append(InlineKeyboardButton(f"{mark}{n}ov", callback_data=f"gs_ol_set_{n}"))
    off_mark = "✅ " if cur_ol == 0 else ""
    buttons = [
        opt_row,
        [InlineKeyboardButton(f"{off_mark}Off (no limit)", callback_data="gs_ol_set_0")],
        [InlineKeyboardButton("🔙 Back", callback_data="gs_home")],
    ]
    return text, InlineKeyboardMarkup(buttons)


# ─── Command ──────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("settings") & filters.group)
async def settings_cmd(client: Client, message: Message):
    from config import Config
    if Config.IS_CLONE:
        return await message.reply_text(
            "🔒 <b>/settings is disabled in clone bots.</b>",
            parse_mode=ParseMode.HTML,
        )
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("⚠️ Only group admins can use /settings.", parse_mode=ParseMode.HTML)
    text, markup = await _main_panel(chat_id)
    await message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


# ─── Callbacks ────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^gs_noop$"))
async def gs_noop_cb(client: Client, query: CallbackQuery):
    await query.answer()


@Client.on_callback_query(filters.regex("^gs_close$"))
async def gs_close_cb(client: Client, query: CallbackQuery):
    try:
        await query.message.delete()
    except Exception:
        await query.message.edit_text("✖ Closed.")
    await query.answer()


@Client.on_callback_query(filters.regex("^gs_home$"))
async def gs_home_cb(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    if not await is_group_admin(client, chat_id, query.from_user.id):
        return await query.answer("Admins only!", show_alert=True)
    text, markup = await _main_panel(chat_id)
    try:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception:
        pass
    await query.answer()


@Client.on_callback_query(filters.regex("^gs_premium_help$"))
async def gs_premium_help_cb(client: Client, query: CallbackQuery):
    text = (
        "💎 <b>How to get Premium</b>\n\n"
        "1️⃣ Open <b>@LegacyContact_Bot</b> and send your query\n"
        "2️⃣ Mention the plan you want:\n"
        "   • 🥈 <b>Silver</b> — Spam Free, Ball Timeout, Over Limit\n"
        "   • 🥇 <b>Gold</b> — All Silver + Disabled Numbers + Edge Rule\n"
        "3️⃣ Ask the owner to activate your group\n\n"
        "Once approved, your group unlocks premium features automatically."
    )
    try:
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="gs_home")]]),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    await query.answer()


@Client.on_callback_query(filters.regex(r"^gs_view_\w+$"))
async def gs_view_cb(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    if not await is_group_admin(client, chat_id, query.from_user.id):
        return await query.answer("Admins only!", show_alert=True)
    feature = query.data[len("gs_view_"):]
    text, markup = await _feature_panel(chat_id, feature)
    try:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception:
        pass
    await query.answer()


@Client.on_callback_query(filters.regex(r"^gs_toggle_[\w]+_[01]$"))
async def gs_toggle_cb(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    if not await is_group_admin(client, chat_id, query.from_user.id):
        return await query.answer("Admins only!", show_alert=True)

    parts   = query.data.split("_")
    value   = int(parts[-1])
    feature = "_".join(parts[2:-1])

    if feature == "super_over":
        return await query.answer(
            "🚧 Super Over is still being built and will be available soon. Try the other features for now!",
            show_alert=True,
        )

    prem_keys = {f[0] for f in PREMIUM_FEATURES} | {"ball_timeout"}
    is_prem   = feature in prem_keys
    if is_prem:
        req_plan = next((f[2] for f in PREMIUM_FEATURES if f[0] == feature), "basic")
        premium  = await get_premium(chat_id)
        if not premium or not plan_unlocked(premium, req_plan):
            return await query.answer("🔒 Upgrade your plan to use this feature!", show_alert=True)

    await set_group_setting(chat_id, feature, bool(value))
    await query.answer("✅ Setting updated!")

    try:
        from plugins.utilities.logger import LOG_GROUP_ID
        chat  = query.message.chat
        admin = query.from_user
        if chat.username:
            group_link = f"https://t.me/{chat.username}"
        else:
            clean_id   = str(chat.id).replace("-100", "")
            group_link = f"https://t.me/c/{clean_id}/1"
        feat_label = next(
            (f[1] for f in FREE_FEATURES if f[0] == feature),
            next((f[1] for f in PREMIUM_FEATURES if f[0] == feature), feature),
        )
        state_text    = "✅ Enabled" if value else "❌ Disabled"
        admin_mention = (
            f"<a href='tg://user?id={admin.id}'>"
            f"{_html.escape(admin.first_name or 'Admin')}</a>"
        )
        await client.send_message(
            LOG_GROUP_ID,
            (
                f"⚙️ <b>Setting Changed</b>\n"
                f"──┈┄┄╌╌╌╌┄┄┈──\n"
                f"💬 <b>Group:</b> "
                f"<a href='{group_link}'>{_html.escape(chat.title or 'Group')}</a>\n"
                f"👤 <b>Admin:</b> {admin_mention}\n"
                f"🔧 <b>Setting:</b> {feat_label}\n"
                f"📊 <b>Status:</b> {state_text}"
            ),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception:
        pass

    text, markup = await _feature_panel(chat_id, feature)
    try:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^gs_dn$"))
async def gs_dn_cb(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    if not await is_group_admin(client, chat_id, query.from_user.id):
        return await query.answer("Admins only!", show_alert=True)
    text, markup = await _dn_panel(chat_id)
    try:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception:
        pass
    await query.answer()


@Client.on_callback_query(filters.regex(r"^gs_dn_toggle_[0-6]$"))
async def gs_dn_toggle_cb(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    if not await is_group_admin(client, chat_id, query.from_user.id):
        return await query.answer("Admins only!", show_alert=True)

    premium = await get_premium(chat_id)
    if not premium or not plan_unlocked(premium, "standard"):
        return await query.answer("🔒 Standard plan required!", show_alert=True)

    n        = int(query.data.split("_")[-1])
    settings = await get_group_settings(chat_id)
    dn       = list(settings.get("disabled_numbers", []))

    if n in dn:
        dn.remove(n)
        await query.answer(f"✅ Number {n} re-enabled!")
    else:
        if len(dn) >= 2:
            return await query.answer("⚠️ Max 2 numbers can be blocked!", show_alert=True)
        dn.append(n)
        dn.sort()
        await query.answer(f"🚫 Number {n} blocked!")

    await set_group_setting(chat_id, "disabled_numbers", dn)
    text, markup = await _dn_panel(chat_id)
    try:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^gs_timeout$"))
async def gs_timeout_cb(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    if not await is_group_admin(client, chat_id, query.from_user.id):
        return await query.answer("Admins only!", show_alert=True)
    text, markup = await _timeout_panel(chat_id)
    try:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception:
        pass
    await query.answer()


@Client.on_callback_query(filters.regex(r"^gs_timeout_set_\d+$"))
async def gs_timeout_set_cb(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    if not await is_group_admin(client, chat_id, query.from_user.id):
        return await query.answer("Admins only!", show_alert=True)

    premium = await get_premium(chat_id)
    if not premium or not plan_unlocked(premium, "silver"):
        return await query.answer("🔒 Silver plan required!", show_alert=True)

    secs = int(query.data.split("_")[-1])
    await set_group_setting(chat_id, "ball_timeout", secs)
    await query.answer(f"✅ Timeout set to {_timeout_label(secs)}!")

    text, markup = await _timeout_panel(chat_id)
    try:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^gs_ol$"))
async def gs_ol_cb(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    if not await is_group_admin(client, chat_id, query.from_user.id):
        return await query.answer("Admins only!", show_alert=True)
    text, markup = await _over_limit_panel(chat_id)
    try:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception:
        pass
    await query.answer()


@Client.on_callback_query(filters.regex(r"^gs_ol_set_\d+$"))
async def gs_ol_set_cb(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    if not await is_group_admin(client, chat_id, query.from_user.id):
        return await query.answer("Admins only!", show_alert=True)

    premium = await get_premium(chat_id)
    if not premium or not plan_unlocked(premium, "silver"):
        return await query.answer("🔒 Silver plan required!", show_alert=True)

    n = int(query.data.split("_")[-1])
    await set_group_setting(chat_id, "over_limit", n)
    label = f"{n} over(s) max" if n else "Off (no limit)"
    await query.answer(f"✅ Over limit: {label}!")

    text, markup = await _over_limit_panel(chat_id)
    try:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception:
        pass
