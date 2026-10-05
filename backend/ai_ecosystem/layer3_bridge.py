from __future__ import annotations

import asyncio
from typing import Any

from .layer2_rag_store import search as brain_search, status as brain_status
from .security import bridge_mutations_allowed, sanitize
from ..activity_logger import log_activity


class Layer3Bridge:
    """Safe adapter around legacy routines. Imports happen lazily to prevent cycles."""

    READ_ONLY_ACTIONS = {"health", "logs_search", "brain_search", "automation_status"}
    MUTATING_ACTIONS = {"scrape", "rag_rebuild"}

    async def execute(self, action: str, params: dict[str, Any] | None = None, actor: str = "layer3", confirm: bool = False) -> dict[str, Any]:
        action = str(action or "").strip().lower()
        params = params or {}
        if action not in self.READ_ONLY_ACTIONS | self.MUTATING_ACTIONS:
            raise ValueError(f"Unsupported bridge action: {action}")
        if action in self.MUTATING_ACTIONS and (not bridge_mutations_allowed() or not confirm):
            raise PermissionError("Mutation is disabled. Set AI_BRIDGE_ALLOW_MUTATIONS=true and require explicit confirmation.")
        try:
            if action == "health":
                from ..main import health
                result = health()
            elif action == "logs_search":
                from ..scraper import search_logs
                result = search_logs(query=sanitize(params.get("q", "")), platform=sanitize(params.get("platform", "")), date_from=sanitize(params.get("date_from", "")), date_to=sanitize(params.get("date_to", "")), limit=min(int(params.get("limit", 20)), 100), offset=0)
            elif action == "brain_search":
                result = {"results": brain_search(sanitize(params.get("q", "")), min(int(params.get("top_k", 6)), 20))}
            elif action == "automation_status":
                from ..main import automation
                result = automation()
            elif action == "rag_rebuild":
                from ..rag_store import rebuild_index
                result = rebuild_index()
            elif action == "scrape":
                from ..scraper import scrape_and_save
                result = await asyncio.to_thread(scrape_and_save, topic=sanitize(params.get("topic", "")), platform=sanitize(params.get("platform", "All Platforms")), storage_mode=sanitize(params.get("storage_mode", "append")), file_name=sanitize(params.get("file_name", "ai_bridge_test")))
            else:
                raise ValueError("Unhandled action")
            safe = sanitize(result)
            log_activity(source="layer3", actor=actor, action=action, command=f"bridge:{action}", output=safe, metadata={"mutation": action in self.MUTATING_ACTIONS})
            return {"ok": True, "action": action, "result": safe, "brain": brain_status()}
        except Exception as exc:
            log_activity(source="layer3", actor=actor, action=action, command=f"bridge:{action}", status="error", output=sanitize(str(exc)))
            raise

    async def chat(self, message: str, actor: str = "layer3") -> dict[str, Any]:
        text = sanitize(message).strip()
        lower = text.lower()
        if any(k in lower for k in ("health", "status", "uptime")):
            action, params = "health", {}
        elif "search logs" in lower or "logs" in lower:
            action, params = "logs_search", {"q": text}
        elif "brain" in lower or "knowledge" in lower:
            action, params = "brain_search", {"q": text}
        elif "automation" in lower or "scheduler" in lower:
            action, params = "automation_status", {}
        else:
            return {"ok": True, "mode": "safe-chat", "answer": "I can audit health, search logs, inspect the local brain, or inspect automation. Use the execution API for an explicitly approved mutation."}
        return await self.execute(action, params, actor=actor, confirm=False)
