from __future__ import annotations

import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import SETTINGS
from memory import MEMORY, UserState
from swarm import CLIENT, run_single_chat, run_swarm, web_research

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("telegram-swarm-bot")

APP_NAME = "LITHOVEX Swarm Bot"
SWARM_ONLY_NOTICE = "Premium required. Swarm agents are available for premium users and admins only."
WEB_ONLY_NOTICE = "Premium required. Web research mode is available for premium users and admins only."

def is_admin(user: UserState | None) -> bool:
    return bool(user and user.role == "admin")

def is_premium(user: UserState | None) -> bool:
    return bool(user and (user.role in {"premium", "admin"} or user.premium == 1))

def esc(text: str) -> str:
    return html.escape(text or "")

def menu_keyboard(user: UserState | None) -> InlineKeyboardMarkup:
    premium = is_premium(user)
    buttons = [
        [InlineKeyboardButton("💬 Chat", callback_data="mode:chat")],
        [InlineKeyboardButton("📚 Web", callback_data="mode:web") if premium else InlineKeyboardButton("🔒 Web", callback_data="locked:web")],
        [InlineKeyboardButton("🧠 Swarm", callback_data="mode:swarm") if premium else InlineKeyboardButton("🔒 Swarm", callback_data="locked:swarm")],
        [InlineKeyboardButton("📋 Help", callback_data="menu:help"), InlineKeyboardButton("👤 Profile", callback_data="menu:profile")],
    ]
    return InlineKeyboardMarkup(buttons)

def help_text(user: UserState | None) -> str:
    role = user.role if user else "normal"
    premium = "yes" if is_premium(user) else "no"
    return f"""<b>{APP_NAME} Help</b>

<b>Your role:</b> {esc(role)}
<b>Premium:</b> {premium}

<b>Commands</b>
/start - open menu
/help - show this help
/chat - normal single-model chat
/swarm - premium multi-agent mode
/web &lt;query&gt; - premium live web research
/web on|off - toggle web mode for your chat replies
/status - show your mode and access
/profile - show your account info
/agents - show the agent lineup
/memory - show memory status
/clear - clear your chat history
/myid - show your Telegram user ID

<b>Admin commands</b>
/premium &lt;user_id&gt; on|off - grant or revoke premium
/role &lt;user_id&gt; normal|premium|admin - set a role
/users - list recent users
"""

def agent_text() -> str:
    return """<b>Agent lineup</b>

• Researcher
• Analyst
• Planner
• Writer
• Critic
• Implementer

Premium users can use the swarm and web research modes."""

def profile_text(user: UserState | None) -> str:
    if not user:
        return "No profile found yet."
    username = f"@{esc(user.username)}" if user.username else "unknown"
    return f"""<b>Your profile</b>

<b>User ID:</b> <code>{user.user_id}</code>
<b>Username:</b> {username}
<b>Role:</b> {esc(user.role)}
<b>Mode:</b> {esc(user.mode)}
<b>Web toggle:</b> {'on' if user.web_enabled else 'off'}
<b>Premium:</b> {'yes' if is_premium(user) else 'no'}"""

def status_text(user: UserState | None) -> str:
    if not user:
        return "No user state yet."
    allowed = "swarm + web + chat" if is_premium(user) else "chat only"
    return f"""<b>Status</b>

<b>Current mode:</b> {esc(user.mode)}
<b>Web toggle:</b> {'on' if user.web_enabled else 'off'}
<b>Allowed:</b> {allowed}
<b>Role:</b> {esc(user.role)}"""

async def safe_send_long(update: Update, text: str, *, reply_markup=None) -> None:
    if not update.message:
        return
    max_len = 3900
    parts = [text[i:i + max_len] for i in range(0, len(text), max_len)] or [""]
    for idx, part in enumerate(parts):
        await update.message.reply_text(
            part,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=reply_markup if idx == 0 else None,
        )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)
    text = f"""<b>Welcome to {APP_NAME}</b>

A polished Telegram AI assistant with:
• single-model chat for everyone
• premium swarm mode for approved users
• premium live web research
• admin controls
• memory
• clean menu UI

Use the buttons below or type /help."""
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=menu_keyboard(user),
        disable_web_page_preview=True,
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)
    await safe_send_long(update, help_text(user))

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)
    await update.message.reply_text(profile_text(user), parse_mode=ParseMode.HTML)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)
    await update.message.reply_text(status_text(user), parse_mode=ParseMode.HTML)

async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(agent_text(), parse_mode=ParseMode.HTML)

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: <code>{update.effective_user.id}</code>", parse_mode=ParseMode.HTML)

async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """<b>Memory</b>

This bot stores chat history in SQLite per user.
Use /clear to wipe your messages.""",
        parse_mode=ParseMode.HTML,
    )

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)
    await MEMORY.clear_history(user.user_id)
    await update.message.reply_text("🧹 Your chat history has been cleared.")

async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)
    await MEMORY.set_mode(user.user_id, "chat")
    await update.message.reply_text("💬 Chat mode enabled. Normal single-model replies are active.")

async def cmd_swarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)
    if not is_premium(user):
        await update.message.reply_text(f"🔒 {SWARM_ONLY_NOTICE}\n\nUse /chat for the normal mode.")
        return
    await MEMORY.set_mode(user.user_id, "swarm")
    await update.message.reply_text("🧠 Swarm mode enabled. Premium agents will be used.")

async def cmd_web(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)

    if context.args:
        arg0 = context.args[0].lower()
        if arg0 in {"on", "off", "enable", "disable"}:
            if not is_premium(user):
                await update.message.reply_text(f"🔒 {WEB_ONLY_NOTICE}")
                return
            enabled = arg0 in {"on", "enable"}
            await MEMORY.set_web(user.user_id, enabled)
            await update.message.reply_text(f"🌐 Web mode {'enabled' if enabled else 'disabled'} for your chat replies.")
            return

        if not is_premium(user):
            await update.message.reply_text(f"🔒 {WEB_ONLY_NOTICE}")
            return

        query = " ".join(context.args)
        await update.message.chat.send_action(action="typing")
        history = await MEMORY.get_history(user.user_id, 8)
        try:
            result = await web_research(query, history)
        except Exception as exc:
            log.exception("web research failed")
            result = f"⚠️ Web research failed right now.\n\n<code>{esc(str(exc))[:1500]}</code>"
        await MEMORY.add_message(user.user_id, "user", f"[WEB] {query}")
        await MEMORY.add_message(user.user_id, "assistant", result)
        await safe_send_long(update, f"<b>Web Research</b>\n\n{esc(result)}")
        return

    await update.message.reply_text("Usage: /web <query> or /web on|off")

async def cmd_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)
    if not is_admin(user):
        await update.message.reply_text("⛔ Admin only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /premium <user_id> on|off")
        return
    target_id = int(context.args[0])
    action = context.args[1].lower()
    target = await MEMORY.get_user(target_id)
    if target is None:
        await update.message.reply_text("User not found in database yet. Ask them to /start first.")
        return
    await MEMORY.set_premium(target_id, action in {"on", "true", "yes", "1"})
    if action in {"on", "true", "yes", "1"}:
        await MEMORY.set_role(target_id, "premium" if target.role != "admin" else "admin")
        await update.message.reply_text(f"✅ Premium granted to {target_id}.")
    else:
        if target.role == "premium":
            await MEMORY.set_role(target_id, "normal")
        await update.message.reply_text(f"✅ Premium removed from {target_id}.")

async def cmd_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)
    if not is_admin(user):
        await update.message.reply_text("⛔ Admin only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /role <user_id> normal|premium|admin")
        return
    target_id = int(context.args[0])
    role = context.args[1].lower()
    if role not in {"normal", "premium", "admin"}:
        await update.message.reply_text("Role must be normal, premium, or admin.")
        return
    target = await MEMORY.get_user(target_id)
    if target is None:
        await update.message.reply_text("User not found in database yet. Ask them to /start first.")
        return
    await MEMORY.set_role(target_id, role)
    await update.message.reply_text(f"✅ Role for {target_id} set to {role}.")

async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)
    if not is_admin(user):
        await update.message.reply_text("⛔ Admin only.")
        return
    rows = await MEMORY.list_users(20)
    if not rows:
        await update.message.reply_text("No users yet.")
        return
    lines = ["<b>Recent users</b>\n"]
    for row in rows:
        uname = row["username"] or "unknown"
        lines.append(f"• <code>{row['user_id']}</code> | @{esc(uname)} | {esc(row['role'])} | {esc(row['mode'])} | web:{'on' if row['web_enabled'] else 'off'}")
    await safe_send_long(update, "\n".join(lines))

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user = await MEMORY.ensure_user(query.from_user.id, query.from_user.username)
    data = query.data or ""
    if data == "menu:help":
        await query.message.reply_text(help_text(user), parse_mode=ParseMode.HTML)
        return
    if data == "menu:profile":
        await query.message.reply_text(profile_text(user), parse_mode=ParseMode.HTML)
        return
    if data == "mode:chat":
        await MEMORY.set_mode(user.user_id, "chat")
        await query.message.reply_text("💬 Chat mode enabled.")
        return
    if data == "mode:swarm":
        if not is_premium(user):
            await query.message.reply_text(f"🔒 {SWARM_ONLY_NOTICE}")
            return
        await MEMORY.set_mode(user.user_id, "swarm")
        await query.message.reply_text("🧠 Swarm mode enabled.")
        return
    if data == "mode:web":
        if not is_premium(user):
            await query.message.reply_text(f"🔒 {WEB_ONLY_NOTICE}")
            return
        await MEMORY.set_web(user.user_id, True)
        await query.message.reply_text("🌐 Web mode enabled.")
        return
    if data.startswith("locked:"):
        await query.message.reply_text("🔒 This feature is premium only.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = await MEMORY.ensure_user(update.effective_user.id, update.effective_user.username)
    text = update.message.text.strip()

    if text.startswith("/"):
        return

    await MEMORY.add_message(user.user_id, "user", text)
    history = await MEMORY.get_history(user.user_id, 12)

    mode = user.mode if user.mode in {"chat", "swarm"} else "chat"
    if mode == "swarm" and not is_premium(user):
        mode = "chat"
        await MEMORY.set_mode(user.user_id, "chat")

    await update.message.chat.send_action(action="typing")

    try:
        if mode == "swarm":
            result = await run_swarm(text, history, use_web_search=bool(user.web_enabled))
        else:
            result = await run_single_chat(text, history, use_web_search=bool(user.web_enabled))
    except Exception as exc:
        log.exception("model call failed")
        result = f"⚠️ The model call failed right now.\n\n<code>{esc(str(exc))[:1500]}</code>"

    await MEMORY.add_message(user.user_id, "assistant", result)
    await safe_send_long(update, f"<b>{APP_NAME}</b>\n\n{esc(result)}")

async def post_init(app: Application) -> None:
    await MEMORY.init()
    await CLIENT.open()
    log.info("%s started", APP_NAME)

async def post_shutdown(app: Application) -> None:
    await CLIENT.close()

def build_app() -> Application:
    if not SETTINGS.bot_token:
        raise RuntimeError("BOT_TOKEN is missing. Set it in .env or Railway variables.")

    app = (
        ApplicationBuilder()
        .token(SETTINGS.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("agents", cmd_agents))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("chat", cmd_chat))
    app.add_handler(CommandHandler("swarm", cmd_swarm))
    app.add_handler(CommandHandler("web", cmd_web))
    app.add_handler(CommandHandler("premium", cmd_premium))
    app.add_handler(CommandHandler("role", cmd_role))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app

if __name__ == "__main__":
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)
