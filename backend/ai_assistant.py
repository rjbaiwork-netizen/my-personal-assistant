from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
CONFIG_PATH = STORAGE_DIR / "config.json"

# Gemini's current fast general-purpose model. Environment configuration wins.
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MODEL_FALLBACKS = ("gemini-3.8-flash", "gemini-3.5-flash-lite")


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _api_key() -> str:
    # Never log or return this value. Cloud environment secret has priority.
    return str(
        os.getenv("GEMINI_API_KEY")
        or _load_config().get("gemini_api_key")
        or ""
    ).strip()


def _configured_model() -> str:
    configured = str(_load_config().get("gemini_model") or "").strip()
    return os.getenv("GEMINI_MODEL", configured or DEFAULT_MODEL).strip()


def _request(model: str, key: str, prompt: str) -> tuple[str | None, str | None, int]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        response = requests.post(
            url,
            params={"key": key},
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ]
            },
            timeout=45,
            headers={"Content-Type": "application/json"},
        )
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not response.ok:
            detail = data.get("error", {}).get("message", f"HTTP {response.status_code}")
            return None, detail, response.status_code
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        answer = "".join(
            str(part.get("text", "")) for part in parts if part.get("text")
        ).strip()
        return answer or None, None, response.status_code
    except requests.RequestException as exc:
        return None, f"{type(exc).__name__}", 0


def chat_with_gemini(message: str, context: str = "") -> str:
    key = _api_key()
    if not key:
        return "Gemini API key is not configured. Set GEMINI_API_KEY in Railway or use Admin & Settings."

    prompt = (
        "You are a concise personal AI assistant. Help analyze the user's data and answer clearly. "
        "Do not invent scraped facts. If context is provided, distinguish it from your own reasoning.\n\n"
        f"DATA CONTEXT:\n{context[:20000]}\n\nUSER:\n{message}"
    )

    configured = _configured_model()
    candidates = []
    for model in (configured, *MODEL_FALLBACKS):
        if model and model not in candidates:
            candidates.append(model)

    last_error = "Unknown Gemini API error."
    for model in candidates:
        answer, error, status = _request(model, key, prompt)
        if answer:
            return answer
        last_error = error or last_error
        # A model-not-found/access error should automatically try the current fallback.
        if status not in {400, 403, 404}:
            break

    return f"Gemini request failed: {last_error}"
