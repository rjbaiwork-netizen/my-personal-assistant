from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .layer1_manager import Layer1Manager
from .layer2_rag_store import search as brain_search, status as brain_status
from .layer3_bridge import Layer3Bridge
from .security import authorized, sanitize

router = APIRouter()
layer1 = Layer1Manager()
layer3 = Layer3Bridge()


def _auth(secret: str) -> None:
    if not authorized(secret):
        raise HTTPException(status_code=401, detail="AI ecosystem authentication failed.")


class ChatPayload(BaseModel):
    message: str = Field(min_length=1, max_length=10000)


class ExecutePayload(BaseModel):
    action: str = Field(min_length=1, max_length=50)
    params: dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False


@router.get("/api/ai/health")
def ai_health() -> dict[str, Any]:
    return {"ok": True, "subsystem": "three-layer-ai-ecosystem", "layer2": brain_status(), "layer1": layer1.telemetry()}


@router.get("/api/ai/profiles")
def profiles(x_ai_ecosystem_secret: str = Header(default="")) -> dict[str, Any]:
    _auth(x_ai_ecosystem_secret)
    return {"layer1": {"model": "configured via legacy runtime", "secret": "masked"}, "layer2": brain_status(), "layer3": {"mutation_enabled": __import__("os").getenv("AI_BRIDGE_ALLOW_MUTATIONS", "false").lower() == "true"}}


@router.post("/api/layer1/chat")
def layer1_chat(payload: ChatPayload, x_ai_ecosystem_secret: str = Header(default="")) -> dict[str, Any]:
    _auth(x_ai_ecosystem_secret)
    return layer1.execute(payload.message, actor="operator")


@router.get("/api/layer2/status")
def layer2_status(x_ai_ecosystem_secret: str = Header(default="")) -> dict[str, Any]:
    _auth(x_ai_ecosystem_secret)
    return brain_status()


@router.get("/api/layer2/search")
def layer2_search(q: str, top_k: int = 6, x_ai_ecosystem_secret: str = Header(default="")) -> dict[str, Any]:
    _auth(x_ai_ecosystem_secret)
    return {"results": brain_search(sanitize(q), top_k)}


@router.post("/api/layer3/chat")
async def layer3_chat(payload: ChatPayload, x_ai_ecosystem_secret: str = Header(default="")) -> dict[str, Any]:
    _auth(x_ai_ecosystem_secret)
    return await layer3.chat(payload.message, actor="operator")


@router.post("/api/layer3/execute")
async def layer3_execute(payload: ExecutePayload, x_ai_ecosystem_secret: str = Header(default="")) -> dict[str, Any]:
    _auth(x_ai_ecosystem_secret)
    try:
        return await layer3.execute(payload.action, payload.params, actor="operator", confirm=payload.confirm)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/ai/telemetry")
def telemetry(x_ai_ecosystem_secret: str = Header(default="")) -> dict[str, Any]:
    _auth(x_ai_ecosystem_secret)
    return {"layer1": layer1.telemetry(), "layer2": brain_status()}
