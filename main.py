from __future__ import annotations

import logging
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import load_settings
from memory import MemoryStore
from swarm import LithovexClient, should_use_swarm


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("telegram-swarm-bot")

SETTINGS = load_settings()
STORE = MemoryStore(SETTINGS.db_path)


async def send_long_text(update: Update, text: str) -> None:
    if not update.message:
        return
    chunks = split_message(text, limit=3900)
    for chunk in chunks:
        try:
            await update.message.reply_text(
                chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except BadRequest:
            await update.message.reply_text(
                chunk,
                disable_web_page_preview=True,
            )


def split_message(text: str, limit: int = 3900) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""

    for paragraph in text.split("\n"):
        candidate = paragraph if not current else current + "\n" + paragraph
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        while len(paragraph) > limit:
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]


def format_agent_summary(outputs: dict[str, str]) -> str:
    lines = ["<b>Swarm summary</b>"]
    for name, output in outputs.items():
        preview = escape(output[:350]).replace("\n", " ")
        lines.append(f"• <b>{escape(name)}</b>: {preview}")
    return "\n".join(lines)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    await STORE.set_setting(update.effective_user.id, "mode", "auto")
    await STORE.set_setting(update.effective_user.id, "memory", "on")
    await STORE.set_setting(update.effective_user.id, "web", "off")

    msg = (
        "🚀 <b>Swarm Bot is ready</b>\n\n"
        "It can do:\n"
        "• multi-agent replies\n"
        "• direct chat mode\n"
        "• conversation memory\n"
        "• web-search flag passthrough\n"
        "• /mode switching\n\n"
        "Try /help to see commands."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    msg = (
        "<b>Commands</b>\n"
        "/start - initialize bot\n"
        "/help - show this help\n"
        "/mode auto|swarm|chat|fast - change reply mode\n"
        "/web on|off - toggle web-search flag\n"
        "/memory on|off - enable/disable memory\n"
        "/agents - show agent list\n"
        "/status - show current settings\n"
        "/clear - clear your chat history\n\n"
        "Send any normal message after that."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    if not context.args:
        await update.message.reply_text("Usage: /mode auto|swarm|chat|fast")
        return

    mode = context.args[0].lower().strip()
    if mode not in {"auto", "swarm", "chat", "fast"}:
        await update.message.reply_text("Invalid mode. Use: auto, swarm, chat, fast")
        return

    await STORE.set_setting(update.effective_user.id, "mode", mode)
    await update.message.reply_text(f"Mode set to: {mode}")


async def cmd_web(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    if not context.args:
        await update.message.reply_text("Usage: /web on|off")
        return

    value = context.args[0].lower().strip()
    if value not in {"on", "off"}:
        await update.message.reply_text("Use /web on or /web off")
        return

    await STORE.set_setting(update.effective_user.id, "web", value)
    await update.message.reply_text(f"Web mode set to: {value}")


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    if not context.args:
        await update.message.reply_text("Usage: /memory on|off")
        return

    value = context.args[0].lower().strip()
    if value not in {"on", "off"}:
        await update.message.reply_text("Use /memory on or /memory off")
        return

    await STORE.set_setting(update.effective_user.id, "memory", value)
    await update.message.reply_text(f"Memory set to: {value}")


async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "Agents: Researcher, Analyst, Implementer, Critic, Planner, Writer"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    mode = await STORE.get_setting(update.effective_user.id, "mode", "auto")
    memory = await STORE.get_setting(update.effective_user.id, "memory", "on")
    web = await STORE.get_setting(update.effective_user.id, "web", "off")

    await update.message.reply_text(
        f"Mode: {mode}\nMemory: {memory}\nWeb: {web}\nBase URL: {SETTINGS.base_url}"
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    await STORE.clear_history(update.effective_user.id)
    await update.message.reply_text("Conversation history cleared.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        return

    mode = await STORE.get_setting(user_id, "mode", "auto") or "auto"
    memory_enabled = (await STORE.get_setting(user_id, "memory", "on") or "on") == "on"
    use_web_search = (await STORE.get_setting(user_id, "web", "off") or "off") == "on"

    history = await STORE.get_recent_messages(user_id, SETTINGS.max_history_turns) if memory_enabled else []

    await STORE.add_message(user_id, "user", text)

    progress = await update.message.reply_text("🧠 Thinking...")

    try:
        async with LithovexClient(SETTINGS) as client:
            if should_use_swarm(mode, text):
                final, outputs = await client.run_swarm(text, history, use_web_search)
                response_text = final
                if mode == "swarm":
                    response_text = final + "\n\n" + format_agent_summary(outputs)
            else:
                response_text = await client.direct_reply(text, history, use_web_search)

        await STORE.add_message(user_id, "assistant", response_text)
        await send_long_text(update, response_text)

    except Exception as exc:
        log.exception("Failed to handle message")
        await update.message.reply_text(f"❌ Error: {exc}")
    finally:
        try:
            await progress.delete()
        except Exception:
            pass


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Telegram update error: %s", context.error)


async def post_init(app: Application) -> None:
    await STORE.init()
    log.info("Database initialized at %s", SETTINGS.db_path)


def build_app() -> Application:
    app = Application.builder().token(SETTINGS.bot_token).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CommandHandler("web", cmd_web))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("agents", cmd_agents))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(on_error)
    return app


def main() -> None:
    app = build_app()
    print("🚀 Telegram Swarm Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
