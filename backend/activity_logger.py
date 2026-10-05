from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
ACTIVITY_PATH = STORAGE_DIR / "activity.jsonl"
_lock = threading.RLock()

_SECRET_FIELDS = {"api_key", "gemini_api_key", "telegram_bot_token", "token", "secret", "password"}

def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): ("••••••••" if str(k).lower() in _SECRET_FIELDS else _safe(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    text = str(value)
    lowered = text.lower()
    if any(marker in lowered for marker in ("api_key=", "bot_token=", "x-admin-config-secret", "authorization: bearer")):
        return "[redacted]"
    return text

def log_activity(
    *,
    source: str,
    action: str,
    status: str = "success",
    actor: str = "system",
    command: str | None = None,
    output: Any = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "actor": actor,
        "action": action,
        "command": command or action,
        "status": status,
        "output": _safe(output),
        "metadata": _safe(metadata or {}),
    }
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _lock:
        with ACTIVITY_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return record

def recent_activity(limit: int = 100, source: str = "", status: str = "") -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    records: list[dict[str, Any]] = []
    if not ACTIVITY_PATH.exists():
        return records
    with _lock:
        lines = ACTIVITY_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if source and item.get("source") != source:
            continue
        if status and item.get("status") != status:
            continue
        records.append(item)
        if len(records) >= limit:
            break
    return records

def activity_status() -> dict[str, Any]:
    try:
        size = ACTIVITY_PATH.stat().st_size if ACTIVITY_PATH.exists() else 0
    except OSError:
        size = 0
    return {"path": str(ACTIVITY_PATH), "size_bytes": size}
