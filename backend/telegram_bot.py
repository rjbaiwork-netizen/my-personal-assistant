from __future__ import annotations

import os
from typing import Awaitable, Callable

from fastapi import Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .backup_rotation import create_rotated_backup, upload_to_s3
from .scraper import scrape_and_save
from .security_monitor import system_metrics
from .telegram_notifier import telegram_configured
from .config_manager import get, update, public, set_runtime_environment
from .activity_logger import log_activity

_app: Application | None = None
_scrape_callback: Callable[[str], Awaitable[dict]] | None = None


def _authorized(update: Update) -> bool:
    allowed = str(get("telegram_chat_id", os.getenv("TELEGRAM_CHAT_ID", "")) or "").strip()
    chat = update.effective_chat
    return bool(chat) and (not allowed or str(chat.id) == allowed)

def _actor(update: Update) -> str:
    user = update.effective_user
    chat = update.effective_chat
    name = (user.username or user.full_name) if user else ""
    return f"{name} (chat:{chat.id})" if chat else (name or "telegram")

def _command(update: Update) -> str:
    text = update.effective_message.text if update.effective_message else ""
    return (text.split()[0] if text else "telegram_command").strip()

def _apply(values: dict) -> dict:
    config = update(**values)
    set_runtime_environment(config)
    return config

def _reload_runtime() -> dict:
    config = read_config()
    set_runtime_environment(config)
    from .main import automation_scheduler
    status = automation_scheduler.reload() if automation_scheduler else {"enabled": False, "jobs": []}
    return {"config": public(config), "scheduler": status}

def read_config():
    from .config_manager import read
    return read()

async def _setkey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    command = _command(update); actor = _actor(update)
    if not _authorized(update):
        log_activity(source="telegram", actor=actor, action="unauthorized", command=command, status="error", output="Unauthorized command")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setkey <Gemini API key>"); return
    _apply({"gemini_api_key": context.args[0].strip()})
    log_activity(source="telegram", actor=actor, action="setkey", command=command, output="Gemini API key updated")
    await update.message.reply_text("✅ Gemini API key updated and active immediately.")

async def _setmodel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    command = _command(update); actor = _actor(update)
    if not _authorized(update):
        log_activity(source="telegram", actor=actor, action="unauthorized", command=command, status="error", output="Unauthorized command")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setmodel <model_name>"); return
    model = context.args[0].strip()
    _apply({"gemini_model": model})
    log_activity(source="telegram", actor=actor, action="setmodel", command=command, output={"model": model})
    await update.message.reply_text(f"✅ Gemini model changed to {model}.")

async def _setinterval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    command = _command(update); actor = _actor(update)
    if not _authorized(update):
        log_activity(source="telegram", actor=actor, action="unauthorized", command=command, status="error", output="Unauthorized command")
        return
    try:
        minutes = int(context.args[0])
        if not 1 <= minutes <= 10080: raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /setinterval <1-10080 minutes>"); return
    _apply({"scrape_interval_minutes": minutes})
    os.environ["SCRAPE_INTERVAL_MINUTES"] = str(minutes)
    result = _reload_runtime()
    log_activity(source="telegram", actor=actor, action="setinterval", command=command, output={"minutes": minutes, "scheduler": result["scheduler"]})
    await update.message.reply_text(f"✅ Scrape interval changed to {minutes} minutes.")

async def _reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    command = _command(update); actor = _actor(update)
    if not _authorized(update):
        log_activity(source="telegram", actor=actor, action="unauthorized", command=command, status="error", output="Unauthorized command")
        return
    result = _reload_runtime()
    log_activity(source="telegram", actor=actor, action="reload", command=command, output=result["scheduler"])
    await update.message.reply_text("♻️ Runtime configuration reloaded.\n" + str(result["scheduler"]))

async def _status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    command = _command(update); actor = _actor(update)
    if not _authorized(update):
        log_activity(source="telegram", actor=actor, action="unauthorized", command=command, status="error", output="Unauthorized command")
        return
    metrics = system_metrics()
    summary = (
        "🤖 My Personal Assistant\n"
        f"CPU {metrics['cpu_percent']}% · RAM {metrics['memory_percent']}% · Disk {metrics['disk_percent']}%\n"
        f"Telegram configured: {telegram_configured()}"
    )
    log_activity(source="telegram", actor=actor, action="status", command=command, output=summary)
    await update.message.reply_text(summary)


async def _scrape(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    command = _command(update); actor = _actor(update)
    if not _authorized(update):
        log_activity(source="telegram", actor=actor, action="unauthorized", command=command, status="error", output="Unauthorized command")
        return
    topic = " ".join(context.args).strip()
    if not topic:
        await update.message.reply_text("Usage: /scrape <topic>")
        return
    if _scrape_callback:
        result = await _scrape_callback(topic)
    else:
        result = scrape_and_save(topic, "All Platforms", "append", "telegram_scrape")
    log_activity(source="telegram", actor=actor, action="scrape", command=command, output=result, metadata={"topic": topic})
    await update.message.reply_text(
        f"🔎 Scrape complete\nFile: {result.get('file_name')}\nRows: {result.get('rows_added', 0)}"
    )


async def _backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    command = _command(update); actor = _actor(update)
    if not _authorized(update):
        log_activity(source="telegram", actor=actor, action="unauthorized", command=command, status="error", output="Unauthorized command")
        return
    path = create_rotated_backup()
    log_activity(source="telegram", actor=actor, action="backup", command=command, output={"file": path.name})
    await update.message.reply_text(f"💾 Backup complete\n{path.name}")


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor = _actor(update); command = _command(update)
    log_activity(source="telegram", actor=actor, action="start", command=command, output="Bot help displayed")
    await update.message.reply_text(
        "My Personal Assistant bot is ready.\n"
        "/scrape <topic> — run a scrape\n/status — system status\n/backup — create a backup\n/setkey <key> — update Gemini key\n/setmodel <model> — change model\n/setinterval <minutes> — change scrape interval\n/reload — reload runtime"
    )


def configure_scrape_callback(callback: Callable[[str], Awaitable[dict]]) -> None:
    global _scrape_callback
    _scrape_callback = callback


def build_application() -> Application | None:
    global _app
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return None
    _app = Application.builder().token(token).build()
    _app.add_handler(CommandHandler("start", _start))
    _app.add_handler(CommandHandler("status", _status))
    _app.add_handler(CommandHandler("scrape", _scrape))
    _app.add_handler(CommandHandler("backup", _backup))
    _app.add_handler(CommandHandler("setkey", _setkey))
    _app.add_handler(CommandHandler("setmodel", _setmodel))
    _app.add_handler(CommandHandler("setinterval", _setinterval))
    _app.add_handler(CommandHandler("reload", _reload))
    return _app


async def initialize() -> bool:
    app = _app or build_application()
    if not app:
        return False
    if not app.running:
        await app.initialize()
    return True


async def shutdown() -> None:
    if _app:
        if _app.running:
            await _app.stop()
        await _app.shutdown()


async def handle_webhook(request: Request) -> dict[str, bool]:
    app = _app or build_application()
    if not app:
        return {"ok": False}
    await initialize()
    payload = await request.json()
    update = Update.de_json(payload, app.bot)
    await app.process_update(update)
    return {"ok": True}


def validate_mini_app_init_data(init_data: str, max_age_seconds: int = 86400) -> bool:
    import hashlib, hmac, time
    from urllib.parse import parse_qsl
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or not init_data:
        return False
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", "")
    auth_date = int(pairs.get("auth_date", "0") or 0)
    if not received or not auth_date or time.time() - auth_date > max_age_seconds:
        return False
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)
