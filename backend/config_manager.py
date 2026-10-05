from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/app/storage")).resolve()
CONFIG_PATH = STORAGE_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "platform_name": "My Personal Assistant",
    "logo": "🤖",
    "gemini_api_key": "",
    "gemini_model": "gemini-3.7-flash",
    "default_storage_mode": "append",
    "scrape_interval_minutes": 60,
}

_SECRET_KEYS = {"gemini_api_key", "telegram_bot_token", "webhook_secret", "telegram_webhook_secret", "aws_secret_access_key"}
_lock = RLock()


def _normalise(data: dict[str, Any]) -> dict[str, Any]:
    result = {**DEFAULTS, **data}
    for key in ("gemini_api_key", "telegram_bot_token", "webhook_secret", "telegram_webhook_secret", "aws_secret_access_key"):
        if key in result and result[key] is None:
            result[key] = ""
    return result


def read() -> dict[str, Any]:
    with _lock:
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return _normalise(data if isinstance(data, dict) else {})
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULTS)


def write(updates: dict[str, Any], *, replace: bool = False) -> dict[str, Any]:
    if not isinstance(updates, dict):
        raise ValueError("Configuration must be an object.")
    with _lock:
        current = {} if replace else read()
        merged = _normalise({**current, **updates})
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=STORAGE_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(merged, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, CONFIG_PATH)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
    return merged


def update(**updates: Any) -> dict[str, Any]:
    return write(updates)


def get(key: str, default: Any = None) -> Any:
    value = read().get(key, default)
    env_name = {
        "gemini_api_key": "GEMINI_API_KEY",
        "gemini_model": "GEMINI_MODEL",
        "scrape_interval_minutes": "SCRAPE_INTERVAL_MINUTES",
        "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    }.get(key)
    if env_name:
        return os.getenv(env_name, value)
    return value


def set_runtime_environment(config: dict[str, Any]) -> None:
    mapping = {
        "gemini_api_key": "GEMINI_API_KEY",
        "gemini_model": "GEMINI_MODEL",
        "scrape_interval_minutes": "SCRAPE_INTERVAL_MINUTES",
        "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    }
    for key, env_name in mapping.items():
        if key in config and config[key] not in (None, ""):
            os.environ[env_name] = str(config[key])


def public(config: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(config or read())
    for key in _SECRET_KEYS:
        if data.get(key):
            data[key] = "••••••••"
    return data
