from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import psutil

from .telegram_notifier import send_telegram_notification

_last_alert: dict[str, float] = {}


def system_metrics() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": memory.percent,
        "disk_percent": disk.percent,
        "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def check_resource_pressure() -> dict[str, Any]:
    metrics = system_metrics()
    threshold = float(os.getenv("RESOURCE_ALERT_PERCENT", "90"))
    overloaded = any(
        metrics[key] >= threshold for key in ("cpu_percent", "memory_percent", "disk_percent")
    )
    now = time.time()
    if overloaded and now - _last_alert.get("resource", 0) > 900:
        _last_alert["resource"] = now
        await send_telegram_notification(
            "🚨 Resource alert",
            f"CPU: {metrics['cpu_percent']}%\nMemory: {metrics['memory_percent']}%\nDisk: {metrics['disk_percent']}%",
        )
    return {"overloaded": overloaded, "threshold": threshold, **metrics}


async def alert_unauthorized(path: str, detail: str = "Unauthorized request") -> None:
    if os.getenv("SECURITY_ALERTS_ENABLED", "true").lower() != "true":
        return
    await send_telegram_notification(
        "🛡️ Security alert",
        f"{detail}\nPath: {path}\nTime: {datetime.now(timezone.utc).isoformat()}",
    )
