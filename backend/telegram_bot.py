from __future__ import annotations

import os
from typing import Awaitable, Callable

from fastapi import Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .backup_rotation import create_rotated_backup
from .scraper import scrape_and_save
from .security_monitor import system_metrics
from .telegram_notifier import telegram_configured

_app: Application | None = None
_scrape_callback: Callable[[str], Awaitable[dict]] | None = None


async def _status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    metrics = system_metrics()
    await update.message.reply_text(
        "🤖 My Personal Assistant\n"
        f"CPU {metrics['cpu_percent']}% · RAM {metrics['memory_percent']}% · Disk {metrics['disk_percent']}%\n"
        f"Telegram configured: {telegram_configured()}"
    )


async def _scrape(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    topic = " ".join(context.args).strip()
    if not topic:
        await update.message.reply_text("Usage: /scrape <topic>")
        return
    if _scrape_callback:
        result = await _scrape_callback(topic)
    else:
        result = scrape_and_save(topic, "All Platforms", "append", "telegram_scrape")
    await update.message.reply_text(
        f"🔎 Scrape complete\nFile: {result.get('file_name')}\nRows: {result.get('rows_added', 0)}"
    )


async def _backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    path = create_rotated_backup()
    await update.message.reply_text(f"💾 Backup complete\n{path.name}")


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "My Personal Assistant bot is ready.\n"
        "/scrape <topic> — run a scrape\n/status — system status\n/backup — create a backup"
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
