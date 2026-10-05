from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
CONFIG_PATH = STORAGE_DIR / "config.json"
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _api_key() -> str:
    # Environment secret takes precedence over the UI-managed config value.
    return str(os.getenv("GEMINI_API_KEY") or _load_config().get("gemini_api_key") or "").strip()


def chat_with_gemini(message: str, context: str = "") -> str:
    key = _api_key()
    if not key:
        return "Gemini API key is not configured. Set GEMINI_API_KEY or use Admin & Settings."

    config = _load_config()
    model = str(config.get("gemini_model") or DEFAULT_MODEL)
    prompt = (
        "You are a concise personal AI assistant. Help analyze the user's data and answer clearly. "
        "Do not invent scraped facts. If context is provided, distinguish it from your own reasoning.\n\n"
        f"DATA CONTEXT:\n{context[:20000]}\n\nUSER:\n{message}"
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        response = requests.post(
            url,
            params={"key": key},
            json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
            timeout=45,
            headers={"Content-Type": "application/json"},
        )
        data = response.json()
        if not response.ok:
            detail = data.get("error", {}).get("message", f"HTTP {response.status_code}")
            return f"Gemini request failed: {detail}"
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        answer = "".join(p.get("text", "") for p in parts).strip()
        return answer or "Gemini returned an empty response."
    except (requests.RequestException, ValueError) as exc:
        return f"Gemini connection failed: {type(exc).__name__}."
