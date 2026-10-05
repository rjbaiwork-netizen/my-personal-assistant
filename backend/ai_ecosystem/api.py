from __future__ import annotations
from typing import Any
import os
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from .layer1_manager import Layer1Manager
from .layer2_rag_store import search as brain_search, status as brain_status
from .layer3_bridge import Layer3Bridge
from .security import authorized, sanitize

router=APIRouter(tags=["AI Ecosystem"])
layer1=Layer1Manager()
layer3=Layer3Bridge()

def _auth(secret:str)->None:
    if not authorized(secret):
        raise HTTPException(status_code=401,detail="AI ecosystem authentication failed.")

class ChatPayload(BaseModel):
    message:str=Field(min_length=1,max_length=10000)

class ExecutePayload(BaseModel):
    action:str=Field(min_length=1,max_length=50)
    params:dict[str,Any]=Field(default_factory=dict)
    confirm:bool=False

def _secret(x_ai_ecosystem_secret:str=Header(default="",alias="X-AI-Ecosystem-Secret")):
    _auth(x_ai_ecosystem_secret)

@router.get("/api/ai/health")
def ai_health()->dict[str,Any]:
    return {"ok":True,"subsystem":"three-layer-ai-ecosystem","layer1":layer1.telemetry(),"layer2":brain_status(),"layer3":layer3.telemetry()}

@router.get("/api/ai/profiles")
def profiles(_:None=__import__("fastapi").Depends(_secret))->dict[str,Any]:
    from ..config_manager import read as read_config
    config=read_config()
    return {"layer1":{"model":config.get("gemini_model","gemini-3.7-flash"),"fallbacks":["gemini-3.7-flash","gemini-3.5-flash-lite"],"api_key":"configured" if config.get("gemini_api_key") or os.getenv("GEMINI_API_KEY") else "not_configured"},"layer2":brain_status(),"layer3":{"mutation_enabled":os.getenv("AI_BRIDGE_ALLOW_MUTATIONS","false").lower()=="true","default_mutation":False,"confirmation_required":True}}

@router.get("/api/ai/telemetry")
def telemetry(_:None=__import__("fastapi").Depends(_secret))->dict[str,Any]:
    from ..config_manager import read as read_config
    c=read_config()
    return {"layer1":{**layer1.telemetry(),"model":c.get("gemini_model","gemini-3.7-flash")},"layer2":brain_status(),"layer3":layer3.telemetry()}

@router.get("/api/layer2/status")
def layer2_status(_:None=__import__("fastapi").Depends(_secret))->dict[str,Any]:
    return brain_status()

@router.get("/api/layer2/search")
def layer2_search(q:str=Query(min_length=1,max_length=2000),top_k:int=Query(default=6,ge=1,le=20),_:None=__import__("fastapi").Depends(_secret))->dict[str,Any]:
    return {"results":brain_search(sanitize(q),top_k)}

@router.post("/api/layer1/chat")
def layer1_chat(payload:ChatPayload,_:None=__import__("fastapi").Depends(_secret))->dict[str,Any]:
    return layer1.execute(payload.message,actor="operator")

@router.post("/api/layer3/chat")
async def layer3_chat(payload:ChatPayload,_:None=__import__("fastapi").Depends(_secret))->dict[str,Any]:
    return await layer3.chat(payload.message,actor="operator")

@router.get("/api/layer3/status")
def layer3_status(_:None=__import__("fastapi").Depends(_secret))->dict[str,Any]:
    return layer3.telemetry()

@router.post("/api/layer3/execute")
async def layer3_execute(payload:ExecutePayload,_:None=__import__("fastapi").Depends(_secret))->dict[str,Any]:
    try:
        return await layer3.execute(payload.action,payload.params,actor="operator",confirm=payload.confirm)
    except PermissionError as exc:
        raise HTTPException(status_code=403,detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc
