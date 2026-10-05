from __future__ import annotations

import os
from typing import Iterable

from telegram import Bot

MAX_MESSAGE_LENGTH = 4000


def telegram_configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


async def _send_chunks(bot: Bot, chat_id: str, text: str) -> None:
    for start in range(0, len(text), MAX_MESSAGE_LENGTH):
        await bot.send_message(chat_id=chat_id, text=text[start:start + MAX_MESSAGE_LENGTH])


async def send_telegram_notification(title: str, body: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False

    message = f"{title}\n\n{body}".strip()
    try:
        async with Bot(token=token) as bot:
            await _send_chunks(bot, chat_id, message)
        return True
    except Exception:
        # Notification failure must never fail the user's primary task.
        return False


async def notify_scrape(result: dict) -> bool:
    if os.getenv("TELEGRAM_NOTIFY_SCRAPE", "true").lower() != "true":
        return False
    return await send_telegram_notification(
        "🔎 Scrape completed",
        "\n".join([
            f"Topic: {result.get('records', [{}])[0].get('Prompt/Topic', 'N/A')}",
            f"File: {result.get('file_name', 'N/A')}",
            f"Rows added: {result.get('rows_added', 0)}",
            f"Total rows: {result.get('total_rows', 0)}",
            f"Mode: {result.get('storage_mode', 'N/A')}",
        ]),
    )


async def notify_ai(message: str, answer: str) -> bool:
    if os.getenv("TELEGRAM_NOTIFY_AI", "true").lower() != "true":
        return False
    return await send_telegram_notification(
        "🧠 AI task completed",
        f"Request: {message[:800]}\n\nAnswer:\n{answer[:2800]}",
    )


async def notify_backup(filename: str, destination: str = "local") -> bool:
    if os.getenv("TELEGRAM_NOTIFY_BACKUP", "true").lower() != "true":
        return False
    return await send_telegram_notification(
        "💾 Backup completed",
        f"File: {filename}\nDestination: {destination}",
    )
