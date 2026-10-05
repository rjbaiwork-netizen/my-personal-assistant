from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ai_assistant import chat_with_gemini
from scraper import list_excel_files, read_logs, scrape_and_save

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
CONFIG_PATH = STORAGE_DIR / "config.json"
BACKUP_DIR = STORAGE_DIR / "backups"
FRONTEND_DIR = BASE_DIR / "frontend"
STORAGE_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

DEFAULT_CONFIG = {
    "platform_name": "My Personal Assistant",
    "logo": "🤖",
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "default_storage_mode": "append",
}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def save_config(config: dict[str, Any]) -> None:
    STORAGE_DIR.mkdir(exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


class ScrapeRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=1000)
    platform: str = "All Platforms"
    storage_mode: str = "append"
    file_name: str = "scrape_log"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    include_logs: bool = True


class SettingsRequest(BaseModel):
    platform_name: str = Field(default="My Personal Assistant", max_length=100)
    logo: str = Field(default="🤖", max_length=20)
    gemini_api_key: str = Field(default="", max_length=500)
    gemini_model: str = Field(default="gemini-2.5-flash", max_length=100)
    default_storage_mode: str = "append"


app = FastAPI(title="My Personal Assistant API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "online", "service": "my-personal-assistant"}


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    config = load_config().copy()
    config["gemini_api_key"] = "••••••••" if config.get("gemini_api_key") else ""
    return config


@app.post("/api/settings")
def update_settings(payload: SettingsRequest) -> dict[str, Any]:
    current = load_config()
    incoming = payload.model_dump()
    if incoming["gemini_api_key"] == "••••••••":
        incoming["gemini_api_key"] = current.get("gemini_api_key", "")
    save_config(incoming)
    return {"ok": True, "settings": get_settings()}


@app.post("/api/scrape")
def trigger_scrape(payload: ScrapeRequest) -> dict[str, Any]:
    try:
        return {"ok": True, **scrape_and_save(**payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/logs")
def logs(limit: int = 100) -> dict[str, Any]:
    return {"records": read_logs(max(1, min(limit, 500)) )}


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    context = ""
    if payload.include_logs:
        context = json.dumps(read_logs(100), ensure_ascii=False, default=str)
    return {"answer": chat_with_gemini(payload.message, context)}


@app.get("/api/excel")
def excel_files() -> dict[str, Any]:
    return {"files": list_excel_files()}


@app.get("/api/download-excel/{file_name}")
def download_excel(file_name: str):
    safe_name = Path(file_name).name
    path = STORAGE_DIR / "excel_files" / safe_name
    if path.suffix.lower() != ".xlsx" or not path.exists():
        raise HTTPException(status_code=404, detail="Excel file not found.")
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def create_backup() -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "my-personal-assistant"
        root.mkdir()
        for item in BASE_DIR.iterdir():
            if item.name in {".git", "storage"}:
                continue
            if item.name.startswith("."):
                continue
            destination = root / item.name
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)

        # Copy storage while deliberately excluding old backups and redacting the API key.
        storage_copy = root / "storage"
        storage_copy.mkdir()
        for item in STORAGE_DIR.iterdir():
            if item.name == "backups":
                continue
            destination = storage_copy / item.name
            if item.name == "config.json":
                config = load_config()
                config["gemini_api_key"] = ""
                destination.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
            elif item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)

        archive = shutil.make_archive(str(BACKUP_DIR / "system_backup"), "zip", root_dir=tmp, base_dir=root.name)
    return Path(archive)


@app.post("/api/backup")
def backup():
    try:
        path = create_backup()
        return FileResponse(path, filename=path.name, media_type="application/zip")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}") from exc


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/{path:path}")
def frontend(path: str):
    candidate = (FRONTEND_DIR / path).resolve()
    if candidate.is_file() and FRONTEND_DIR.resolve() in candidate.parents:
        return FileResponse(candidate)
    return FileResponse(FRONTEND_DIR / "index.html")
