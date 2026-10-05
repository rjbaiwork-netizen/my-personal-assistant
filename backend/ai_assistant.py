from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
CONFIG_PATH = STORAGE_DIR / "config.json"
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
MODEL_FALLBACKS = ("gemini-3.7-flash", "gemini-3.5-flash-lite")


def _load_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _api_key() -> str:
    return str(os.getenv("GEMINI_API_KEY") or _load_config().get("gemini_api_key") or "").strip()


def _configured_model() -> str:
    configured = str(_load_config().get("gemini_model") or "").strip()
    return os.getenv("GEMINI_MODEL", configured or DEFAULT_MODEL).strip()


def _request(model: str, key: str, prompt: str) -> tuple[str | None, str | None, int]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        response = requests.post(
            url,
            params={"key": key},
            json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
            timeout=45,
            headers={"Content-Type": "application/json"},
        )
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not response.ok:
            return None, data.get("error", {}).get("message", f"HTTP {response.status_code}"), response.status_code
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        answer = "".join(str(p.get("text", "")) for p in parts if p.get("text")).strip()
        return answer or None, None, response.status_code
    except requests.RequestException as exc:
        return None, type(exc).__name__, 0


def _generate(prompt: str) -> str:
    key = _api_key()
    if not key:
        return "Gemini API key is not configured. Set GEMINI_API_KEY in Railway or Admin Settings."
    candidates = []
    for model in (_configured_model(), *MODEL_FALLBACKS):
        if model and model not in candidates:
            candidates.append(model)
    last_error = "Unknown Gemini API error."
    for model in candidates:
        answer, error, status = _request(model, key, prompt)
        if answer:
            return answer
        last_error = error or last_error
        if status not in {400, 403, 404}:
            break
    return f"Gemini request failed: {last_error}"


def scraping_agent(topic: str) -> str:
    return _generate(
        "You are the Scraping Agent. Create a safe public-web extraction plan for this topic. "
        "Prefer stable semantic signals, metadata, headings and links; never bypass authentication, CAPTCHA, "
        "robots restrictions or access controls. Return concise JSON-like guidance.\nTOPIC: " + topic
    )


def analyst_agent(topic: str, context: str, scrape_plan: str = "") -> str:
    return _generate(
        "You are the Analyst Agent. Analyze supplied records and distinguish evidence from inference. "
        "Find trends, anomalies, duplicates and useful conclusions. Do not invent facts.\n"
        f"TOPIC: {topic}\nSCRAPE PLAN:\n{scrape_plan[:5000]}\nDATA:\n{context[:18000]}"
    )


def report_writer_agent(topic: str, analysis: str) -> str:
    return _generate(
        "You are the Report Writer Agent. Turn the analysis into a concise actionable report with "
        "Executive Summary, Key Findings, Risks, and Recommended Actions.\n"
        f"TOPIC: {topic}\nANALYSIS:\n{analysis[:16000]}"
    )


def chat_with_gemini(message: str, context: str = "") -> str:
    return _generate(
        "You are the primary personal AI assistant. Answer clearly and concisely. "
        "Use retrieved context as evidence and explicitly say when the data is insufficient.\n"
        f"DATA CONTEXT:\n{context[:20000]}\n\nUSER:\n{message}"
    )
