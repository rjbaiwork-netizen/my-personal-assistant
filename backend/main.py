from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .ai_assistant import chat_with_gemini
from .scraper import COLUMNS, EXCEL_DIR, list_excel_files, read_logs, scrape_and_save, search_logs
from .backup_rotation import backup_status, create_rotated_backup, upload_to_s3, sync_excel_to_s3, cleanup_remote_backups
from .scheduler import AutomationScheduler
from .telegram_notifier import notify_ai, notify_backup, notify_scrape, telegram_configured, send_telegram_notification
from .rag_store import context_for, rebuild_index, search as rag_search
from .agent_workflow import run_multi_agent_workflow
from .rss_worker import recent_items, sync_feeds
from .security_monitor import alert_unauthorized, check_resource_pressure
from .telegram_bot import configure_scrape_callback, handle_webhook, initialize as initialize_telegram_bot, shutdown as shutdown_telegram_bot, validate_mini_app_init_data
from .config_manager import read as read_dynamic_config, update as update_dynamic_config, public as public_config, set_runtime_environment
from .activity_logger import log_activity, recent_activity, activity_status

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
CONFIG_PATH = STORAGE_DIR / "config.json"
BACKUP_DIR = STORAGE_DIR / "backups"
FRONTEND_DIR = BASE_DIR / "frontend"
RUNTIME_PATH = STORAGE_DIR / "runtime.json"

for directory in (STORAGE_DIR, EXCEL_DIR, BACKUP_DIR):
    directory.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "platform_name": "My Personal Assistant",
    "logo": "🤖",
    "gemini_api_key": "",
    "gemini_model": "gemini-3.7-flash",
    "default_storage_mode": "append",
}


def load_config() -> dict[str, Any]:
    return read_dynamic_config()

def _legacy_load_config_disabled() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        save_config(dict(DEFAULT_CONFIG))
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return {**DEFAULT_CONFIG, **data}
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def save_config(config: dict[str, Any]) -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(CONFIG_PATH)


def apply_runtime_config(updates: dict[str, Any]) -> dict[str, Any]:
    config = update_dynamic_config(**updates)
    set_runtime_environment(config)
    if "scrape_interval_minutes" in updates:
        os.environ["SCRAPE_INTERVAL_MINUTES"] = str(config["scrape_interval_minutes"])
    if automation_scheduler:
        automation_scheduler.reload()
    return config

def _today() -> str:
    return datetime.now(timezone.utc).astimezone().date().isoformat()


def _load_runtime() -> dict[str, Any]:
    default = {
        "date": _today(),
        "server_runtime_seconds": 0,
        "last_tick": time.time(),
    }
    if not RUNTIME_PATH.exists():
        return default
    try:
        data = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
        if data.get("date") != default["date"]:
            return default
        return {**default, **data}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default


def _save_runtime(data: dict[str, Any]) -> None:
    temporary = RUNTIME_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(RUNTIME_PATH)


def record_server_runtime() -> dict[str, Any]:
    now = time.time()
    state = _load_runtime()
    previous = float(state.get("last_tick", now))
    delta = max(0.0, now - previous)
    # Do not count a long sleep/restart gap as active runtime.
    delta = min(delta, 120.0)
    state["server_runtime_seconds"] = round(
        float(state.get("server_runtime_seconds", 0)) + delta, 3
    )
    state["last_tick"] = now
    _save_runtime(state)
    seconds = int(state["server_runtime_seconds"])
    limit = 8 * 60 * 60
    return {
        "date": state["date"],
        "server_runtime_seconds": seconds,
        "limit_seconds": limit,
        "remaining_seconds": max(0, limit - seconds),
        "percent": min(100, round(seconds / limit * 100, 2)),
        "server_started_at": app.state.started_at,
    }


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
    gemini_model: str = Field(default="gemini-3.7-flash", max_length=100)
    default_storage_mode: str = "append"


app = FastAPI(title="My Personal Assistant API", version="3.1.0")
automation_scheduler: AutomationScheduler | None = None

async def scheduled_rss_sync() -> None:
    await asyncio.to_thread(sync_feeds)

async def scheduled_weekly_report() -> None:
    items = await asyncio.to_thread(recent_items, 20)
    if not items:
        return
    context = json.dumps(items, ensure_ascii=False)
    answer = await asyncio.to_thread(chat_with_gemini, "Create a weekly technology-feed summary with key themes and actions.", context)
    await send_telegram_notification("📰 Weekly AI/RSS summary", answer[:3800])

async def scheduled_security_check() -> None:
    await check_resource_pressure()

async def telegram_scrape_callback(topic: str) -> dict[str, Any]:
    result = await asyncio.to_thread(scrape_and_save, topic, "All Platforms", "append", "telegram_scrape")
    await notify_scrape(result)
    return result

@app.on_event("startup")
async def startup() -> None:
    global automation_scheduler
    app.state.started_at = datetime.now(timezone.utc).astimezone().isoformat()
    record_server_runtime()
    automation_scheduler = AutomationScheduler(run_scheduled_scrape, run_scheduled_backup, scheduled_rss_sync, scheduled_weekly_report, scheduled_security_check)
    configure_scrape_callback(telegram_scrape_callback)
    await initialize_telegram_bot()
    automation_scheduler.start()

@app.on_event("shutdown")
async def shutdown() -> None:
    if automation_scheduler:
        automation_scheduler.shutdown()
    await shutdown_telegram_bot()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    config = load_config()
    gemini_key_configured = bool(os.getenv("GEMINI_API_KEY") or config.get("gemini_api_key"))
    gemini_model = str(
        os.getenv("GEMINI_MODEL")
        or config.get("gemini_model")
        or "gemini-3.7-flash"
    ).strip()

    storage_writable = False
    storage_error = None
    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=STORAGE_DIR,
            prefix=".health-",
            suffix=".tmp",
            delete=False,
        ) as probe:
            probe.write("ok")
            probe_path = Path(probe.name)
        probe_path.unlink(missing_ok=True)
        storage_writable = True
    except OSError as exc:
        storage_error = type(exc).__name__

    return {
        "status": "online" if storage_writable else "degraded",
        "service": "my-personal-assistant",
        "version": "3.1.0",
        "storage_dir": str(STORAGE_DIR),
        "storage_writable": storage_writable,
        "storage_error": storage_error,
        "gemini": {
            "configured": gemini_key_configured,
            "model": gemini_model,
            "api_key_exposed": False,
        },
    }


@app.get("/api/usage")
def usage() -> dict[str, Any]:
    return record_server_runtime()

@app.get("/api/activity")
def activity(limit: int = 100, source: str = "", status: str = "") -> dict[str, Any]:
    return {"records": recent_activity(limit, source, status), "storage": activity_status()}

@app.get("/api/automation")
def automation() -> dict[str, Any]:
    return {
        "scheduler": automation_scheduler.status() if automation_scheduler else {"enabled": False, "jobs": []},
        "telegram": {"configured": telegram_configured()},
        "backup": backup_status(),
    }

async def run_scheduled_scrape() -> None:
    topic = os.getenv("SCRAPE_TOPIC", "").strip()
    if not topic:
        return
    result = await asyncio.to_thread(
        scrape_and_save,
        topic=topic,
        platform=os.getenv("SCRAPE_PLATFORM", "All Platforms"),
        storage_mode=os.getenv("SCRAPE_STORAGE_MODE", "append"),
        file_name=os.getenv("SCRAPE_FILE_NAME", "scheduled_scrape"),
    )
    await notify_scrape(result)

async def run_scheduled_backup() -> None:
    path = await asyncio.to_thread(create_rotated_backup)
    destination = "local"
    try:
        await asyncio.to_thread(sync_excel_to_s3)
        await asyncio.to_thread(cleanup_remote_backups)
        remote = await asyncio.to_thread(upload_to_s3, path)
        if remote:
            destination = remote
    except Exception:
        destination = "local (remote upload failed)"
    await notify_backup(path.name, destination)


class AdminConfigRequest(BaseModel):
    gemini_api_key: str | None = Field(default=None, max_length=500)
    gemini_model: str | None = Field(default=None, max_length=100)
    scrape_interval_minutes: int | None = Field(default=None, ge=1, le=10080)
    platform_name: str | None = Field(default=None, max_length=100)
    logo: str | None = Field(default=None, max_length=20)
    default_storage_mode: str | None = None

@app.get("/api/admin/config")
def admin_config():
    return public_config()

@app.post("/api/admin/config")
def admin_update_config(payload: AdminConfigRequest, request: Request):
    import hmac
    expected = os.getenv("ADMIN_CONFIG_SECRET", "").strip()
    supplied = request.headers.get("X-Admin-Config-Secret", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Admin configuration authentication failed.")
    values = payload.model_dump(exclude_none=True)
    if values.get("default_storage_mode") not in (None, "append", "new"):
        raise HTTPException(status_code=400, detail="default_storage_mode must be append or new.")
    if not values:
        raise HTTPException(status_code=400, detail="No configuration changes supplied.")
    current = read_dynamic_config()
    if values.get("gemini_api_key") in ("", "••••••••"):
        values["gemini_api_key"] = current.get("gemini_api_key", "")
    config = apply_runtime_config(values)
    log_activity(source="admin_api", actor="dashboard", action="config_update", command="/admin/config", output=public_config(config), metadata={"fields": list(values.keys())})
    return {"ok": True, "config": public_config(config), "scheduler": automation_scheduler.status() if automation_scheduler else {"enabled": False, "jobs": []}}

@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    config = load_config().copy()
    config["gemini_api_key"] = "••••••••" if config.get("gemini_api_key") else ""
    return config


@app.post("/api/settings")
def update_settings(payload: SettingsRequest, request: Request) -> dict[str, Any]:
    expected = os.getenv("ADMIN_CONFIG_SECRET", "").strip()
    supplied = request.headers.get("X-Admin-Config-Secret", "")
    if expected and supplied != expected:
        raise HTTPException(status_code=401, detail="Admin configuration authentication failed.")
    if payload.default_storage_mode not in {"append", "new"}:
        raise HTTPException(status_code=400, detail="default_storage_mode must be append or new.")
    current = load_config()
    incoming = payload.model_dump()
    if incoming["gemini_api_key"] in {"••••••••", ""}:
        incoming["gemini_api_key"] = current.get("gemini_api_key", "")
    config = apply_runtime_config(incoming)
    return {"ok": True, "settings": public_config(config)}


@app.post("/api/scrape")
async def trigger_scrape(payload: ScrapeRequest, request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Actor", "dashboard")
    try:
        result = await asyncio.to_thread(scrape_and_save, **payload.model_dump())
        await notify_scrape(result)
        log_activity(source="dashboard", actor=actor, action="scrape", command="/scrape", output=result, metadata=payload.model_dump())
        return {"ok": True, **result}
    except ValueError as exc:
        log_activity(source="dashboard", actor=actor, action="scrape", command="/scrape", status="error", output=str(exc), metadata=payload.model_dump())
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_activity(source="dashboard", actor=actor, action="scrape", command="/scrape", status="error", output=str(exc))
        raise


@app.get("/api/logs")
def logs(limit: int = 100) -> dict[str, Any]:
    return {"records": read_logs(max(1, min(limit, 500)))}

@app.get("/api/logs/search")
def logs_search(
    q: str = "",
    platform: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    return search_logs(
        query=q,
        platform=platform,
        date_from=date_from,
        date_to=date_to,
        limit=max(1, min(limit, 500)),
        offset=max(0, offset),
    )


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Actor", "dashboard")
    context = ""
    if payload.include_logs:
        context = json.dumps(read_logs(100), ensure_ascii=False, default=str)
    rag_context = await asyncio.to_thread(context_for, payload.message, 6)
    context = (context + "\n\nLOCAL RAG CONTEXT:\n" + rag_context) if context else rag_context
    answer = await asyncio.to_thread(chat_with_gemini, payload.message, context)
    await notify_ai(payload.message, answer)
    log_activity(source="dashboard", actor=actor, action="chat", command="/chat", output=answer[:1000], metadata={"message": payload.message[:500]})
    return {"answer": answer}



@app.get("/api/rag/search")
def rag_endpoint(q: str, top_k: int = 6, rebuild: bool = False):
    return {"results": rag_search(q, top_k=top_k, rebuild=rebuild)}

@app.post("/api/rag/rebuild")
def rag_rebuild():
    return {"ok": True, **rebuild_index()}

@app.post("/api/agents/workflow")
async def agents_workflow(payload: ChatRequest):
    context = await asyncio.to_thread(context_for, payload.message, 8)
    result = await asyncio.to_thread(run_multi_agent_workflow, payload.message, context)
    return {"ok": True, "workflow": result}

@app.get("/api/rss")
def rss(limit: int = 20):
    return {"items": recent_items(limit)}

@app.post("/api/rss/sync")
async def rss_sync():
    result = await asyncio.to_thread(sync_feeds)
    return {"ok": True, **result}

@app.get("/api/security")
async def security():
    return await check_resource_pressure()

@app.post("/api/webhooks/trigger")
async def event_trigger(request: Request):
    import hmac
    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    provided = request.headers.get("X-Webhook-Secret", "")
    if secret and not hmac.compare_digest(provided, secret):
        await alert_unauthorized("/api/webhooks/trigger", "Invalid webhook secret")
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")
    payload = await request.json()
    message = str(payload.get("message") or payload.get("prompt") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message or prompt is required.")
    context = await asyncio.to_thread(context_for, message, 6)
    answer = await asyncio.to_thread(chat_with_gemini, message, context)
    await notify_ai(message, answer)
    return {"ok": True, "answer": answer}


@app.post("/api/telegram/miniapp")
async def telegram_miniapp(request: Request):
    payload = await request.json()
    init_data = request.headers.get("X-Telegram-Init-Data") or str(payload.get("initData", ""))
    if not validate_mini_app_init_data(init_data):
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram Mini-App initData.")
    message = str(payload.get("message") or "").strip()
    if not message:
        return {"ok": True, "message": "Mini-App authenticated."}
    context = await asyncio.to_thread(context_for, message, 6)
    answer = await asyncio.to_thread(chat_with_gemini, message, context)
    return {"ok": True, "answer": answer}

@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    import hmac
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret and not hmac.compare_digest(provided, secret):
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret.")
    return await handle_webhook(request)

@app.get("/api/excel")
def excel_files() -> dict[str, Any]:
    return {"files": list_excel_files()}


@app.get("/api/download-excel/{file_name}")
def download_excel(file_name: str):
    safe_name = Path(file_name).name
    path = EXCEL_DIR / safe_name
    if path.suffix.lower() != ".xlsx" or not path.exists():
        raise HTTPException(status_code=404, detail="Excel file not found.")
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _load_pdf_frame(file_name: str | None = None) -> pd.DataFrame:
    frames = []
    if file_name:
        safe_name = Path(file_name).name
        path = EXCEL_DIR / safe_name
        if path.suffix.lower() != ".xlsx" or not path.exists():
            raise HTTPException(status_code=404, detail="Excel file not found.")
        frames.append(pd.read_excel(path))
    else:
        for path in sorted(EXCEL_DIR.glob("*.xlsx")):
            try:
                frames.append(pd.read_excel(path))
            except Exception:
                continue
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    frame = pd.concat(frames, ignore_index=True)
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[COLUMNS].fillna("").astype(str)


def build_logs_pdf(file_name: str | None = None) -> BytesIO:
    frame = _load_pdf_frame(file_name)
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=24,
        leftMargin=24,
        topMargin=28,
        bottomMargin=28,
        title="My Personal Assistant - Data Logs",
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("My Personal Assistant — Data Logs", styles["Title"]),
        Paragraph(
            f"Generated {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
            styles["Normal"],
        ),
        Spacer(1, 12),
    ]
    headers = ["Date", "Time", "File Name", "Prompt / Topic", "Platform", "Message Bubble"]
    data = [[Paragraph(h, styles["Heading5"]) for h in headers]]
    for _, row in frame.iterrows():
        data.append([
            Paragraph(str(row["Date"]), styles["BodyText"]),
            Paragraph(str(row["Time"]), styles["BodyText"]),
            Paragraph(str(row["File Name"]), styles["BodyText"]),
            Paragraph(str(row["Prompt/Topic"]), styles["BodyText"]),
            Paragraph(str(row["Platform"]), styles["BodyText"]),
            Paragraph(str(row["Message Bubble"]), styles["BodyText"]),
        ])
    if len(data) == 1:
        data.append([Paragraph("No records available.", styles["BodyText"])] + [""] * 5)
    table = Table(data, repeatRows=1, colWidths=[55, 55, 95, 130, 70, 280])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    doc.build(story)
    output.seek(0)
    return output


@app.get("/api/download-pdf")
def download_pdf(file_name: str | None = None):
    pdf = build_logs_pdf(file_name)
    stem = Path(file_name).stem if file_name else "all_logs"
    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{stem}_logs.pdf"'},
    )


def create_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_base = BACKUP_DIR / f"system_backup_{stamp}"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "my-personal-assistant"
        root.mkdir()
        for item in BASE_DIR.iterdir():
            if item.name in {".git", "storage"} or item.name.startswith("."):
                continue
            destination = root / item.name
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)

        storage_copy = root / "storage"
        storage_copy.mkdir()
        for item in STORAGE_DIR.iterdir():
            if item.name == "backups":
                continue
            destination = storage_copy / item.name
            if item.name == "config.json":
                config = load_config()
                config["gemini_api_key"] = ""
                destination.write_text(
                    json.dumps(config, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            elif item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)
        archive = shutil.make_archive(str(archive_base), "zip", root_dir=tmp, base_dir=root.name)
    return Path(archive)


@app.post("/api/backup")
async def backup(request: Request):
    actor = request.headers.get("X-Actor", "dashboard")
    try:
        path = await asyncio.to_thread(create_rotated_backup)
        destination = "local"
        try:
            await asyncio.to_thread(sync_excel_to_s3)
            await asyncio.to_thread(cleanup_remote_backups)
            remote = await asyncio.to_thread(upload_to_s3, path)
            if remote:
                destination = remote
        except Exception:
            destination = "local (remote upload failed)"
        await notify_backup(path.name, destination)
        log_activity(source="dashboard", actor=actor, action="backup", command="/backup", output={"file": path.name, "destination": destination})
        return FileResponse(path, filename=path.name, media_type="application/zip")
    except OSError as exc:
        log_activity(source="dashboard", actor=actor, action="backup", command="/backup", status="error", output=str(exc))
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}") from exc


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/{path:path}")
def frontend(path: str):
    candidate = (FRONTEND_DIR / path).resolve()
    if candidate.is_file() and FRONTEND_DIR.resolve() in candidate.parents:
        return FileResponse(candidate)
    raise HTTPException(status_code=404, detail="Page not found.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
