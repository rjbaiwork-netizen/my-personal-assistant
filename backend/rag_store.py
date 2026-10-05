from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(__import__("os").getenv("STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
INDEX_PATH = STORAGE_DIR / "rag_index.json"
EXCEL_DIR = STORAGE_DIR / "excel_files"
PDF_DIR = STORAGE_DIR / "pdf"

TOKEN_RE = re.compile(r"[\\w]{2,}", re.UNICODE)
DIMENSIONS = 384


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def _vector(text: str) -> dict[str, float]:
    values: dict[str, float] = {}
    tokens = _tokens(text)
    if not tokens:
        return values
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % DIMENSIONS
        values[str(idx)] = values.get(str(idx), 0.0) + 1.0
    norm = math.sqrt(sum(v * v for v in values.values())) or 1.0
    return {k: v / norm for k, v in values.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    return sum(value * b.get(key, 0.0) for key, value in a.items())


def _load() -> list[dict[str, Any]]:
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def _save(items: list[dict[str, Any]]) -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INDEX_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INDEX_PATH)


def _documents_from_excel() -> list[dict[str, str]]:
    docs = []
    for path in sorted(EXCEL_DIR.glob("*.xlsx")):
        try:
            frame = pd.read_excel(path).fillna("")
            for _, row in frame.iterrows():
                text = " | ".join(f"{c}: {row.get(c, '')}" for c in frame.columns)
                docs.append({"source": path.name, "text": str(text)})
        except Exception:
            continue
    return docs


def _documents_from_pdf() -> list[dict[str, str]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    docs = []
    for path in sorted(PDF_DIR.glob("*.pdf")):
        try:
            reader = PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            if text:
                docs.append({"source": path.name, "text": text})
        except Exception:
            continue
    return docs


def rebuild_index() -> dict[str, int]:
    docs = _documents_from_excel() + _documents_from_pdf()
    indexed = []
    for doc in docs:
        content_hash = hashlib.sha256(doc["text"].encode("utf-8")).hexdigest()
        indexed.append({
            "id": content_hash,
            "source": doc["source"],
            "text": doc["text"][:12000],
            "vector": _vector(doc["text"]),
        })
    _save(indexed)
    return {"documents": len(indexed)}


def search(query: str, top_k: int = 6, rebuild: bool = False) -> list[dict[str, Any]]:
    items = rebuild_index() if rebuild else None
    index = _load()
    if not index and not items:
        rebuild_index()
        index = _load()
    q = _vector(query)
    ranked = sorted(
        (
            {**item, "score": round(_cosine(q, item.get("vector", {})), 5)}
            for item in index
        ),
        key=lambda item: item["score"],
        reverse=True,
    )
    return [
        {"source": item["source"], "score": item["score"], "text": item["text"]}
        for item in ranked[:max(1, min(top_k, 20))]
    ]


def context_for(query: str, top_k: int = 6) -> str:
    results = search(query, top_k=top_k)
    return "\n\n".join(
        f"[Source: {r['source']} | score={r['score']}]\n{r['text']}"
        for r in results
        if r["score"] > 0
    )
