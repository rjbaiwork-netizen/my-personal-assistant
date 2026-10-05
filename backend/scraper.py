from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(__import__("os").getenv("STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
EXCEL_DIR = STORAGE_DIR / "excel_files"
EXCEL_DIR.mkdir(parents=True, exist_ok=True)
COLUMNS = ["Date", "Time", "File Name", "Prompt/Topic", "Platform", "Message Bubble"]

PLATFORMS = {
    "Google": "https://www.google.com/search?q={query}",
    "Bing": "https://www.bing.com/search?q={query}",
    "DuckDuckGo": "https://html.duckduckgo.com/html/?q={query}",
}


def _safe_filename(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip()).strip("._")
    return value or "scrape_log"


def _unique_path(stem: str) -> Path:
    base = EXCEL_DIR / f"{stem}.xlsx"
    if not base.exists():
        return base
    return EXCEL_DIR / f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"


def _extract_semantic_text(html: str) -> tuple[str, str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    title = (soup.title.get_text(" ", strip=True) if soup.title else "").strip()
    meta = []
    for tag in soup.find_all("meta"):
        name = (tag.get("name") or tag.get("property") or "").lower()
        if name in {"description", "og:description", "twitter:description"} and tag.get("content"):
            meta.append(tag["content"])
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])[:12]]
    body = soup.get_text(" ", strip=True)
    # Self-healing extraction: prefer semantic metadata/headings, then body text.
    parts = [title, *meta, *headings, body[:6000]]
    cleaned = re.sub(r"\s+", " ", " | ".join(p for p in parts if p))
    return title, cleaned[:8000], headings


def _fetch_preview(platform: str, topic: str) -> str:
    template = PLATFORMS.get(platform)
    if not template:
        return "No public connector configured."
    try:
        response = requests.get(
            template.format(query=quote_plus(topic)),
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MyPersonalAssistant/4.0)"},
        )
        response.raise_for_status()
        title, text, headings = _extract_semantic_text(response.text)
        marker = "semantic-fallback" if not headings else "semantic-headings"
        return (
            f"HTTP {response.status_code}; strategy={marker}; title={title[:180]}; "
            f"content={text[:520]}"
        )
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
            frame = pd.concat([existing[COLUMNS], pd.DataFrame(rows, columns=COLUMNS)], ignore_index=True)
        else:
            frame = pd.DataFrame(rows, columns=COLUMNS)
    else:
        path = _unique_path(stem)
        frame = pd.DataFrame(rows, columns=COLUMNS)

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
    files = []
    for path in sorted(EXCEL_DIR.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        files.append({"file_name": path.name, "size_bytes": stat.st_size, "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat()})
    return files


def read_logs(limit: int = 100) -> list[dict[str, Any]]:
    records = []
    for path in sorted(EXCEL_DIR.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            frame = pd.read_excel(path).fillna("")
            records.extend(frame.to_dict("records"))
        except Exception:
            continue
    return records[-max(1, min(limit, 500)):][::-1]


def search_logs(query: str = "", platform: str = "", date_from: str = "", date_to: str = "", limit: int = 100, offset: int = 0) -> dict[str, Any]:
    rows = []
    for path in EXCEL_DIR.glob("*.xlsx"):
        try:
            frame = pd.read_excel(path).fillna("")
            for column in COLUMNS:
                if column not in frame.columns:
                    frame[column] = ""
            rows.extend(frame[COLUMNS].to_dict("records"))
        except Exception:
            continue
    q = query.strip().lower()
    pf = platform.strip().lower()
    def match(row: dict[str, Any]) -> bool:
        if q and q not in " ".join(str(row.get(c, "")) for c in COLUMNS).lower():
            return False
        if pf and str(row.get("Platform", "")).lower() != pf:
            return False
        date = str(row.get("Date", ""))
        if date_from and date < date_from:
            return False
        if date_to and date > date_to:
            return False
        return True
    filtered = [r for r in rows if match(r)]
    filtered.sort(key=lambda r: (str(r.get("Date", "")), str(r.get("Time", ""))), reverse=True)
    start = max(0, offset)
    page = filtered[start:start + max(1, min(limit, 500))]
    return {"records": page, "total": len(filtered), "limit": limit, "offset": start}
