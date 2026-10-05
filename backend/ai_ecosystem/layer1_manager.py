from __future__ import annotations

import time
from typing import Any

from .layer2_rag_store import search as brain_search, status as brain_status, train_from_logs
from .security import sanitize
from ..activity_logger import log_activity
from ..ai_assistant import chat_with_gemini


class Layer1Manager:
    """Administrative Gemini facade. It never imports the FastAPI app."""

    def __init__(self) -> None:
        self.requests = 0
        self.estimated_tokens = 0
        self.total_latency_ms = 0.0

    def telemetry(self) -> dict[str, Any]:
        return {"requests": self.requests, "estimated_tokens": self.estimated_tokens, "avg_latency_ms": round(self.total_latency_ms / self.requests, 2) if self.requests else 0.0}

    def _command_action(self, message: str) -> str:
        text = message.lower()
        if any(x in text for x in ("train", "latest logs", "rebuild brain", "update brain", "sync logs")):
            return "train_logs"
        if any(x in text for x in ("search brain", "knowledge", "find in brain")):
            return "brain_search"
        return "chat"

    def execute(self, message: str, actor: str = "layer1") -> dict[str, Any]:
        safe_message = sanitize(message).strip()
        if not safe_message:
            raise ValueError("Message is required.")
        action = self._command_action(safe_message)
        started = time.perf_counter()
        try:
            if action == "train_logs":
                result = train_from_logs()
                answer = f"Layer 2 training completed: {result['added_or_updated']} records processed; {result['documents']} indexed documents."
            elif action == "brain_search":
                result = brain_search(safe_message, 6)
                answer = {"matches": result}
            else:
                context = brain_search(safe_message, 6)
                prompt = "You are Layer 1, the administrative AI controller. Do not claim to have executed an operation unless the subsystem actually executed it. Respond concisely.\n\nOperator command:\n" + safe_message
                answer = chat_with_gemini(prompt, str(context))
                result = {"answer": sanitize(answer)}
            elapsed = (time.perf_counter() - started) * 1000
            self.requests += 1
            self.total_latency_ms += elapsed
            self.estimated_tokens += max(1, len(safe_message) // 4)
            log_activity(source="layer1", actor=actor, action=action, command="/api/layer1/chat", output=result, metadata={"latency_ms": round(elapsed, 2)})
            return {"ok": True, "action": action, "result": result, "telemetry": self.telemetry(), "brain": brain_status()}
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000
            log_activity(source="layer1", actor=actor, action=action, command="/api/layer1/chat", status="error", output=sanitize(str(exc)), metadata={"latency_ms": round(elapsed, 2)})
            raise
