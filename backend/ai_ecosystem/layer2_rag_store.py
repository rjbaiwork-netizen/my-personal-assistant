from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from .security import sanitize

BASE_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
BRAIN_DIR = STORAGE_DIR / "brains"
INDEX_PATH = BRAIN_DIR / "vector_index.json"
META_PATH = BRAIN_DIR / "brain_meta.json"
_lock = RLock()
TOKEN_RE = re.compile(r"\w{2,}", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _vector(text: str) -> dict[str, float]:
    vec: dict[str, float] = {}
    for token in _tokens(text):
        key = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        vec[key] = vec.get(key, 0.0) + 1.0
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    return sum(value * b.get(key, 0.0) for key, value in a.items())


def _load() -> dict[str, Any]:
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"documents": []}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".ai-brain-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def ensure_storage() -> None:
    for name in ("network", "scraper", "analytics", "datasets"):
        (BRAIN_DIR / name).mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        _write(INDEX_PATH, {"documents": []})


def upsert_documents(documents: list[dict[str, Any]], source: str = "system") -> dict[str, Any]:
    ensure_storage()
    clean = []
    for item in documents:
        text = sanitize(item.get("text", "")).strip()
        if not text:
            continue
        doc_id = hashlib.sha256((source + "|" + str(item.get("id", "")) + "|" + text).encode()).hexdigest()
        clean.append({"id": doc_id, "source": source, "domain": str(item.get("domain", "analytics")), "text": text[:12000], "vector": _vector(text), "updated_at": datetime.now(timezone.utc).isoformat()})
    with _lock:
        current = _load()
        by_id = {d.get("id"): d for d in current.get("documents", [])}
        by_id.update({d["id"]: d for d in clean})
        data = {"version": 1, "documents": list(by_id.values())[-5000:]}
        _write(INDEX_PATH, data)
        _write(META_PATH, {"updated_at": datetime.now(timezone.utc).isoformat(), "documents": len(data["documents"]), "domains": sorted({d.get("domain", "analytics") for d in data["documents"]})})
        by_domain: dict[str, list[dict[str, Any]]] = {}
        for doc in data["documents"]:
            by_domain.setdefault(str(doc.get("domain", "analytics")), []).append(doc)
        for domain, domain_docs in by_domain.items():
            _write(BRAIN_DIR / domain / "brain.json", {"version": 1, "domain": domain, "documents": domain_docs})
    return {"added_or_updated": len(clean), "documents": len(data["documents"]), "path": str(BRAIN_DIR)}


def search(query: str, top_k: int = 6, domain: str = "") -> list[dict[str, Any]]:
    ensure_storage()
    qv = _vector(sanitize(query))
    docs = _load().get("documents", [])
    ranked = []
    for doc in docs:
        if domain and doc.get("domain") != domain:
            continue
        score = _cosine(qv, doc.get("vector", {}))
        if score > 0:
            ranked.append((score, doc))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [{"score": round(score, 4), "source": doc.get("source"), "domain": doc.get("domain"), "text": doc.get("text", "")[:2000]} for score, doc in ranked[:max(1, min(int(top_k), 20))]]


def status() -> dict[str, Any]:
    ensure_storage()
    data = _load()
    size = INDEX_PATH.stat().st_size if INDEX_PATH.exists() else 0
    domains = sorted({d.get("domain", "analytics") for d in data.get("documents", [])})
    excel_count = 0
    log_count = 0
    try:
        from ..scraper import EXCEL_DIR, read_logs
        excel_count = len(list(EXCEL_DIR.glob("*.xlsx")))
        log_count = len(read_logs(500))
    except Exception:
        pass
    return {"path": str(BRAIN_DIR), "index": str(INDEX_PATH), "documents": len(data.get("documents", [])), "domains": domains, "index_bytes": size, "excel_files": excel_count, "recent_log_records": log_count, "healthy": True}


def train_from_logs(limit: int = 200) -> dict[str, Any]:
    from ..scraper import read_logs
    records = read_logs(max(1, min(int(limit), 500)))
    docs = [{"id": f"log-{i}", "domain": "scraper", "text": json.dumps(row, ensure_ascii=False, default=str)} for i, row in enumerate(records)]
    return upsert_documents(docs, source="legacy_logs")


def train_from_text(text: str, domain: str = "network", source: str = "layer1") -> dict[str, Any]:
    return upsert_documents([{"id": hashlib.sha256(text.encode()).hexdigest(), "domain": domain, "text": text}], source=source)
