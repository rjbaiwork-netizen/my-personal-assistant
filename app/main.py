from datetime import datetime,timezone
from pathlib import Path
from fastapi import FastAPI,HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.core.config import settings
from app.db.store import store
from app.layers.layer1 import layer1_chat
from app.layers.layer3 import layer3_chat
from app.services.testing import run_test

app=FastAPI(title=settings.app_name,version="1.0.0")
frontend=Path(__file__).resolve().parent.parent/"frontend"
app.mount("/static",StaticFiles(directory=frontend),name="static")

class ChatRequest(BaseModel): message:str
class TestRequest(BaseModel): target:str; mode:str="read-only"

@app.get("/",include_in_schema=False)
def home(): return FileResponse(frontend/"index.html")

@app.get("/api/health")
def health(): return {"status":"ok","timestamp":datetime.now(timezone.utc).isoformat(),"environment":settings.app_env}

@app.get("/api/profiles")
def profiles():
    return [
      {"id":1,"layer":"Layer 1","name":"AI Engine & Management","chat":True},
      {"id":2,"layer":"Layer 2","name":"Own Brain & Data","chat":False},
      {"id":3,"layer":"Layer 3","name":"Operation & Testing","chat":True}]

@app.get("/api/dashboard")
def dashboard(): return store.dashboard()

@app.post("/api/layer1/chat")
def layer1_endpoint(request:ChatRequest):
    if not request.message.strip(): raise HTTPException(400,"message is required")
    result=layer1_chat(request.message); store.log("layer1.chat",request.message); return result

@app.get("/api/layer2/brain")
def layer2_brain(): return store.brain_summary()

@app.post("/api/layer3/chat")
def layer3_endpoint(request:ChatRequest):
    if not request.message.strip(): raise HTTPException(400,"message is required")
    result=layer3_chat(request.message); store.log("layer3.chat",request.message); return result

@app.get("/api/integration/status")
def integration_status():
    return {"enabled":settings.integration_enabled,"mode":"controlled-bridge","writes_allowed":False}

@app.post("/api/testing/run")
def testing_endpoint(request:TestRequest):
    if not request.target.strip(): raise HTTPException(400,"target is required")
    result=run_test(request.target,request.mode); store.log("testing.run",f"{request.mode}:{request.target}"); return result
