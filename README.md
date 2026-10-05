# My Personal Assistant

A single-user Personal AI & Data Scraper Platform using FastAPI, Pandas/OpenPyXL, ReportLab, vanilla JavaScript and Tailwind CSS.

## Architecture

This project is strictly **multi-page HTML**, not a SPA. Each major module is a separate physical document and navigation uses normal links.

```
my-personal-assistant/
├── backend/
│   ├── main.py
│   ├── scraper.py
│   ├── ai_assistant.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── scraper.html
│   ├── logs.html
│   ├── chat.html
│   ├── admin.html
│   ├── backup.html
│   ├── app.js
│   └── styles.css
├── storage/
│   ├── excel_files/
│   ├── backups/
│   └── config.json
├── Dockerfile
├── render.yaml
└── README.md
```

There is no tab router, no SPA view switching and no hidden section-based application shell. app.js is a shared browser utility loaded by all pages; it does not switch page content.

## Pages

- **index.html** — Dashboard, server status, daily 8-hour reference activity counter and quick actions.
- **scraper.html** — Dedicated scraper page with a popup form for topic, platform, New/Append mode and file name.
- **logs.html** — Dedicated chat-bubble log viewer backed by Excel files.
- **chat.html** — Dedicated Gemini AI chat and log-analysis interface.
- **admin.html** — Dedicated platform name, icon, Gemini model/key and default storage settings.
- **backup.html** — Dedicated Excel downloads, PDF log export and full ZIP backup.

## Backend

### Excel storage

Scrape records are stored in storage/excel_files/*.xlsx with Date, Time, File Name, Prompt/Topic, Platform and Message Bubble.

**Append** reads the existing workbook and adds rows without deleting historical rows. **New file** creates a separate timestamped workbook when the requested name already exists.

The built-in collectors fetch public search pages from Google, Bing and DuckDuckGo and store a fetch diagnostic. They do not bypass authentication, CAPTCHAs, paywalls or private content.

### Downloads

- GET /api/download-excel/{file_name} — individual Excel download.
- GET /api/download-pdf — all stored logs as PDF.
- GET /api/download-pdf?file_name=example.xlsx — one workbook as PDF.

### Gemini

The backend reads the Gemini key from storage/config.json and never returns the plaintext key through GET /api/settings. The Admin page can update the key and model dynamically.

Free-tier availability and quotas are controlled by Google's current account/model limits; this application does not bypass provider restrictions.

### Backup

POST /api/backup creates a timestamped ZIP. Previous backup archives are retained. The backup excludes the backups/ archive directory itself and writes a redacted configuration with an empty Gemini key.

## Local run

Requires Python 3.10+.

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 10000
```

Open http://localhost:10000/index.html.

## Docker

```bash
docker build -t my-personal-assistant .
docker run -p 10000:10000 my-personal-assistant
```

The container honors Render's PORT environment variable and falls back to 10000 locally.

## Render

render.yaml defines a free Docker web service with /api/health as the health check.

**Important:** free/ephemeral cloud instances are not durable storage. Download Excel files or create ZIP/PDF backups regularly if data must survive a restart/redeploy.

## Security and production notes

This is intentionally a single-user personal application and has no multi-user authentication. Before exposing it to untrusted users, add authentication/authorization, rate limiting, strict CORS, HTTPS enforcement and a proper secret manager.

The Gemini API key is kept in local storage/config.json because that is part of the requested architecture. For public production deployment, a platform secret/environment variable is preferable.

Never commit a real API key to Git.