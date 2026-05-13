"""
/settings — per-group feature toggle panel (admins only).

Free    : super_over, ai_summary, achievement_alerts, auto_play_again
Premium : spam_free (Basic+), disabled_numbers (Standard+), edge_rule (Pro),
          ball_timeout (Basic+)

Callback scheme:
  gs_home                       main panel
  gs_view_<feature>             feature sub-panel
  gs_toggle_<feature>_<1|0>     toggle ON/OFF
  gs_dn                         disabled-numbers panel
  gs_dn_toggle_<n>              toggle number n (0-6)
  gs_timeout                    timeout picker panel
  gs_timeout_set_<secs>         set timeout to <secs>
"""

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
]

PREMIUM_FEATURES = [
    ("spam_free",        "🛡 Spam Free",      "basic"),
    ("disabled_numbers", "🔲 Dis. Numbers",   "standard"),
    ("edge_rule",        "⚠️ Edge Rule",       "pro"),
]

TIMEOUT_OPTIONS = [
    (30,  "30s"),
    (60,  "1m"),
    (120, "2m"),
    (150, "2m 30s"),
    (180, "3m"),
    (300, "5m"),
]

FEATURE_DESC = {
    "super_over": (
        "⚡ <b>Super Over on Tie</b>\n\n"
        "When a match ends in a tie, a Super Over is triggered.\n"
        "Each team bats 1 over with 2 batters (striker + non-striker).\n"
        "1 wicket in hand — highest score wins!\n"
        "Double-tie → match declared a Tie."
    ),
    "ai_summary": (
        "🧠 <b>AI Over Summary</b>\n\n"
        "After every over our AI commentator delivers a sharp,\n"
        "funny 2–3 line analysis of what just happened.\n"
        "Powered by Llama 3.1 70B via NVIDIA API."
    ),
    "achievement_alerts": (
        "🔔 <b>Achievement Alerts</b>\n\n"
        "Real-time announcements in the group for:\n"
        "50s, 100s, 150s, 250s, 3-wicket hauls, 5-fors,\n"
        "hat-tricks, ducks, and partnership milestones."
    ),
    "auto_play_again": (
        "🔄 <b>Auto Play Again</b>\n\n"
        "After every match a 'Play Again?' prompt appears\n"
        "in the group so players can quickly start a new game."
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
        "📦 Requires <b>Basic plan</b> or above."
    ),
    "disabled_numbers": (
        "🔲 <b>Disabled Numbers</b>  <i>(Premium)</i>\n\n"
        "Block up to 2 numbers (0–6) from the game entirely.\n"
        "Neither batters nor bowlers can use them.\n\n"
        "Great for custom game modes and tighter strategies.\n\n"
        "📦 Requires <b>Standard plan</b> or above."
    ),
    "edge_rule": (
        "⚠️ <b>Edge Rule</b>  <i>(Premium)</i>\n\n"
        "Batter plays 3 consecutive 0s → warning DM sent.\n"
        "4th consecutive 0 → automatically out!\n\n"
        "Encourages active batting and punishes pure defence.\n\n"
        "📦 Requires <b>Pro plan</b>."
    ),
    "ball_timeout": (
        "⏱ <b>Ball Timeout</b>  <i>(Premium)</i>\n\n"
        "Set how long a player has to respond each ball.\n"
        "Default: <b>1 minute</b>.\n\n"
        "Options: 30s · 1m · 2m · 2m 30s · 3m · 5m\n\n"
        "After the timer → warning, then -6 runs penalty.\n\n"
        "📦 Requires <b>Basic plan</b> or above."
    ),
}

PLAN_LOCK_MSG = {
    "basic":    "🔒 Unlock with <b>Basic Plan</b>.",
    "standard": "🔒 Unlock with <b>Standard Plan</b>.",
    "pro":      "🔒 Unlock with <b>Pro Plan</b>.",
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
    plan_name = PLANS[premium["plan"]]["name"] if premium else None

    # Header
    plan_line = (
        f"✨ <b>Plan:</b> {plan_name}"
        if plan_name else
        "🔓 <b>Free tier</b>  —  contact owner for premium"
    )
    text = (
        "⚙️ <b>GROUP SETTINGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"{plan_line}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🆓 <b>Free Features</b>    💎 <b>Premium Features</b>"
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

    # Separator label row (non-clickable trick — use spacer)
    buttons.append([InlineKeyboardButton("─── 💎 Premium ───", callback_data="gs_noop")])

    # Premium: spam_free + disabled_numbers on one row
    spam_unlocked = premium and plan_unlocked(premium, "basic")
    dn_unlocked   = premium and plan_unlocked(premium, "standard")
    edge_unlocked = premium and plan_unlocked(premium, "pro")
    to_unlocked   = premium and plan_unlocked(premium, "basic")

    # Row: spam_free | disabled_numbers
    spam_status = ("✅" if settings.get("spam_free", False) else "❌") if spam_unlocked else "🔒"
    dn           = settings.get("disabled_numbers", [])
    dn_str       = f"[{', '.join(map(str, dn))}]" if dn else "[none]"
    dn_status    = f"🔲 {dn_str}" if dn_unlocked else "🔒"
    buttons.append([
        InlineKeyboardButton(f"{spam_status} 🛡 Spam Free",    callback_data="gs_view_spam_free"),
        InlineKeyboardButton(f"{dn_status} 🔲 Numbers",        callback_data="gs_dn"),
    ])

    # Row: edge_rule | ball_timeout
    edge_status = ("✅" if settings.get("edge_rule", False) else "❌") if edge_unlocked else "🔒"
    cur_timeout  = settings.get("ball_timeout", 60)
    to_label     = _timeout_label(cur_timeout)
    to_status    = f"⏱ {to_label}" if to_unlocked else "🔒 ⏱ Timeout"
    buttons.append([
        InlineKeyboardButton(f"{edge_status} ⚠️ Edge Rule",    callback_data="gs_view_edge_rule"),
        InlineKeyboardButton(f"{to_status}",                   callback_data="gs_timeout"),
    ])

    buttons.append([InlineKeyboardButton("✖ Close", callback_data="gs_close")])

    return text, InlineKeyboardMarkup(buttons)


async def _feature_panel(chat_id: int, feature: str):
    settings        = await get_group_settings(chat_id)
    premium         = await get_premium(chat_id)
    is_prem_feature = feature in {f[0] for f in PREMIUM_FEATURES} or feature == "ball_timeout"
    req_plan        = next(
        (f[2] for f in PREMIUM_FEATURES if f[0] == feature),
        "basic" if feature == "ball_timeout" else None,
    )
    has_access = not is_prem_feature or (premium and plan_unlocked(premium, req_plan))
    desc       = FEATURE_DESC.get(feature, f"⚙️ <b>{feature}</b>")

    if not has_access:
        lock_msg = PLAN_LOCK_MSG.get(req_plan, "🔒 Upgrade to unlock.")
        text = f"{desc}\n\n━━━━━━━━━━━━━━━━━━━━━\n{lock_msg}"
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="gs_home")]])

    default = False if is_prem_feature else True
    val     = settings.get(feature, default)
    status  = "✅ <b>ON</b>" if val else "❌ <b>OFF</b>"
    text    = f"{desc}\n\n━━━━━━━━━━━━━━━━━━━━━\nStatus: {status}"
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

    if not premium or not plan_unlocked(premium, "standard"):
        text = (
            f"{FEATURE_DESC['disabled_numbers']}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"{PLAN_LOCK_MSG['standard']}"
        )
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="gs_home")]])

    text = (
        "🔲 <b>Disabled Numbers</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Tap a number to toggle it on/off.\n"
        "Up to <b>2 numbers</b> can be blocked at once.\n\n"
        f"🚫 Blocked: <b>{', '.join(map(str, dn)) if dn else 'None'}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━"
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
    unlocked    = premium and plan_unlocked(premium, "basic")

    if not unlocked:
        text = (
            f"{FEATURE_DESC['ball_timeout']}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"{PLAN_LOCK_MSG['basic']}"
        )
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="gs_home")]])

    text = (
        "⏱ <b>Ball Timeout Settings</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Set how long each player has to respond.\n"
        "After timeout → warning → -6 run penalty.\n\n"
        f"🕐 <b>Current:</b> {_timeout_label(cur_timeout)}\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )

    # Build 2-per-row option buttons
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


# ─── Command ──────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("settings") & filters.group)
async def settings_cmd(client: Client, message: Message):
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

    is_prem = feature in {f[0] for f in PREMIUM_FEATURES} or feature == "ball_timeout"
    if is_prem:
        req_plan = next((f[2] for f in PREMIUM_FEATURES if f[0] == feature), "basic")
        premium  = await get_premium(chat_id)
        if not premium or not plan_unlocked(premium, req_plan):
            return await query.answer("🔒 Upgrade your plan to use this feature!", show_alert=True)

    await set_group_setting(chat_id, feature, bool(value))
    await query.answer("✅ Setting updated!")
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
            return await query.answer("🚫 Max 2 numbers can be disabled!", show_alert=True)
        dn.append(n)
        await query.answer(f"🚫 Number {n} disabled!")

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
    if not premium or not plan_unlocked(premium, "basic"):
        return await query.answer("🔒 Basic plan required!", show_alert=True)

    secs = int(query.data.split("_")[-1])
    valid = [s for s, _ in TIMEOUT_OPTIONS]
    if secs not in valid:
        return await query.answer("Invalid option.", show_alert=True)

    await set_group_setting(chat_id, "ball_timeout", secs)
    await query.answer(f"✅ Timeout set to {_timeout_label(secs)}!")
    text, markup = await _timeout_panel(chat_id)
    try:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception:
        pass
