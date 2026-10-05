from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
EXCEL_DIR = STORAGE_DIR / "excel_files"
EXCEL_DIR.mkdir(parents=True, exist_ok=True)

COLUMNS = ["Date", "Time", "File Name", "Prompt/Topic", "Platform", "Message Bubble"]

PLATFORMS = {
    "Google": "https://www.google.com/search?q={query}",
    "Bing": "https://www.bing.com/search?q={query}",
    "DuckDuckGo": "https://html.duckduckgo.com/html/?q={query}",
}


def _safe_filename(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    value = value.strip("._")
    return value or "scrape_log"


def _unique_path(stem: str) -> Path:
    base = EXCEL_DIR / f"{stem}.xlsx"
    if not base.exists():
        return base
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return EXCEL_DIR / f"{stem}_{stamp}.xlsx"


def _fetch_preview(platform: str, topic: str) -> str:
    url_template = PLATFORMS.get(platform)
    if not url_template:
        return "No public connector configured for this platform."
    try:
        url = url_template.format(query=quote_plus(topic))
        response = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; MyPersonalAssistant/3.0; "
                    "+https://github.com/rjbaiwork-netizen/my-personal-assistant)"
                )
            },
        )
        response.raise_for_status()
        text = re.sub(r"\s+", " ", response.text)
        return f"HTTP {response.status_code}; public page fetched ({min(len(text), 240)} chars preview)."
    except requests.RequestException as exc:
        return f"Fetch unavailable: {type(exc).__name__}."


def scrape_and_save(topic: str, platform: str, storage_mode: str, file_name: str) -> dict[str, Any]:
    topic = (topic or "").strip()
    platform = (platform or "All Platforms").strip()
    storage_mode = (storage_mode or "append").lower().strip()
    if not topic:
        raise ValueError("Topic / Keywords is required.")
    if storage_mode not in {"append", "new"}:
        raise ValueError("storage_mode must be 'append' or 'new'.")
    platforms = list(PLATFORMS) if platform == "All Platforms" else [platform]
    unknown = [p for p in platforms if p not in PLATFORMS]
    if unknown:
        raise ValueError(f"Unsupported platform(s): {', '.join(unknown)}")

    stem = _safe_filename(file_name or "scrape_log")
    now = datetime.now(timezone.utc).astimezone()
    rows = []
    for item in platforms:
        preview = _fetch_preview(item, topic)
        rows.append({
            "Date": now.strftime("%Y-%m-%d"),
            "Time": now.strftime("%H:%M:%S"),
            "File Name": stem,
            "Prompt/Topic": topic,
            "Platform": item,
            "Message Bubble": f"[{item}] {topic} — {preview}",
        })

    if storage_mode == "append":
        path = EXCEL_DIR / f"{stem}.xlsx"
        if path.exists():
            existing = pd.read_excel(path)
            for column in COLUMNS:
                if column not in existing.columns:
                    existing[column] = ""
            existing = existing[COLUMNS]
            frame = pd.concat([existing, pd.DataFrame(rows, columns=COLUMNS)], ignore_index=True)
        else:
            frame = pd.DataFrame(rows, columns=COLUMNS)
    else:
        path = _unique_path(stem)
        frame = pd.DataFrame(rows, columns=COLUMNS)

    EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_excel(path, index=False, engine="openpyxl")
    return {
        "file_name": path.name,
        "path": str(path.relative_to(BASE_DIR)),
        "rows_added": len(rows),
        "total_rows": len(frame),
        "storage_mode": storage_mode,
        "records": rows,
    }


def list_excel_files() -> list[dict[str, Any]]:
    EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted(EXCEL_DIR.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True):
        result.append({
            "file_name": path.name,
            "size_bytes": path.stat().st_size,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(),
        })
    return result


def read_logs(limit: int = 100) -> list[dict[str, Any]]:
    EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for path in sorted(EXCEL_DIR.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            frame = pd.read_excel(path).fillna("")
            rows.extend(frame.to_dict(orient="records"))
        except Exception:
            continue
    return rows[-limit:][::-1]


def search_logs(
    query: str = "",
    platform: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    query = query.strip().lower()
    platform = platform.strip().lower()
    frames = []

    for path in EXCEL_DIR.glob("*.xlsx"):
        try:
            frame = pd.read_excel(path).fillna("")
            for column in COLUMNS:
                if column not in frame.columns:
                    frame[column] = ""
            frame = frame[COLUMNS]
            frames.append(frame)
        except Exception:
            continue

    if not frames:
        return {"records": [], "total": 0, "limit": limit, "offset": offset}

    frame = pd.concat(frames, ignore_index=True).fillna("").astype(str)

    if query:
        haystack = frame[COLUMNS].agg(" ".join, axis=1).str.lower()
        frame = frame[haystack.str.contains(query, regex=False, na=False)]

    if platform:
        frame = frame[frame["Platform"].str.lower() == platform]

    if date_from:
        frame = frame[frame["Date"] >= date_from]
    if date_to:
        frame = frame[frame["Date"] <= date_to]

    frame = frame.iloc[::-1]
    total = len(frame)
    page = frame.iloc[max(0, offset):max(0, offset) + max(1, min(limit, 500))]
    return {
        "records": page.to_dict(orient="records"),
        "total": total,
        "limit": limit,
        "offset": offset,
    }
