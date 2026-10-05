from __future__ import annotations

import os
import re
from typing import Any

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d .()\-]{7,}\d)(?!\d)")
SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*[^\s,;]+")


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): ("[REDACTED]" if re.search(r"(?i)(key|token|secret|password|authorization)", str(k)) else sanitize(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    text = str(value)
    text = SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    return text[:12000]


def admin_secret() -> str:
    return str(os.getenv("AI_ECOSYSTEM_SECRET") or os.getenv("ADMIN_CONFIG_SECRET") or "").strip()


def authorized(provided: str) -> bool:
    import hmac
    expected = admin_secret()
    return bool(expected and provided and hmac.compare_digest(provided, expected))


def bridge_mutations_allowed() -> bool:
    return os.getenv("AI_BRIDGE_ALLOW_MUTATIONS", "false").strip().lower() == "true"
