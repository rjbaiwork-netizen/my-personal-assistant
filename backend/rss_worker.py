from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
DB_PATH = STORAGE_DIR / "assistant.db"

DEFAULT_FEEDS = [
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.theverge.com/rss/index.xml",
    "https://hnrss.org/frontpage",
]


def _db() -> sqlite3.Connection:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """CREATE TABLE IF NOT EXISTS rss_items(
        id TEXT PRIMARY KEY, source TEXT, title TEXT, url TEXT,
        summary TEXT, published TEXT, created_at TEXT)"""
    )
    return db


def fetch_feeds() -> list[dict[str, Any]]:
    feeds = [x.strip() for x in os.getenv("RSS_FEEDS", "").split(",") if x.strip()] or DEFAULT_FEEDS
    collected = []
    for url in feeds:
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries[:30]:
                title = str(entry.get("title", "")).strip()
                link = str(entry.get("link", "")).strip()
                summary = str(entry.get("summary", entry.get("description", ""))).strip()
                if not title or not link:
                    continue
                item_id = hashlib.sha256(f"{url}|{link}".encode()).hexdigest()
                collected.append({
                    "id": item_id,
                    "source": url,
                    "title": title,
                    "url": link,
                    "summary": summary[:5000],
                    "published": str(entry.get("published", "")),
                })
        except Exception:
            continue
    return collected


def sync_feeds() -> dict[str, int]:
    db = _db()
    added = 0
    items = fetch_feeds()
    for item in items:
        cur = db.execute(
            """INSERT OR IGNORE INTO rss_items
            (id,source,title,url,summary,published,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (
                item["id"], item["source"], item["title"], item["url"],
                item["summary"], item["published"],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        added += int(cur.rowcount > 0)
    db.commit()
    db.close()
    return {"fetched": len(items), "added": added}


def recent_items(limit: int = 20) -> list[dict[str, Any]]:
    db = _db()
    rows = db.execute(
        "SELECT title,url,summary,published,source FROM rss_items ORDER BY created_at DESC LIMIT ?",
        (max(1, min(limit, 100)),),
    ).fetchall()
    db.close()
    return [
        {"title": r[0], "url": r[1], "summary": r[2], "published": r[3], "source": r[4]}
        for r in rows
    ]
