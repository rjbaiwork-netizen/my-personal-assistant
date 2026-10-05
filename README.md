---
title: My Personal Assistant
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
python_version: "3.10"
app_port: 7860
fullWidth: true
---

# My Personal Assistant

A single-user Personal AI & Data Scraper Platform using FastAPI, Pandas/OpenPyXL, ReportLab, vanilla JavaScript and Tailwind CSS.

## Architecture

Strict multi-page HTML. Each module is a physical HTML document; navigation uses ordinary links. There is no SPA router or tab-switching view system.

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
├── .github/workflows/
│   └── sync-to-huggingface.yml
├── Dockerfile
├── railway.json
└── README.md
```

## Runtime and storage

The API reads `STORAGE_DIR` from the environment and creates all required directories at startup. Local default: `./storage`. Railway should mount a persistent Volume at `/app/storage`. Railway Volumes persist across deploys/restarts, but the volume is mounted only at runtime, so application directories must also be created by the container startup process.

The Dashboard's server usage counter is backed by `storage/runtime.json`. It tracks active server runtime with an 8-hour daily reference limit and intentionally does not count a long sleep/restart gap as active runtime.

## Railway

1. Create a Railway project and connect the GitHub repository `rjbaiwork-netizen/my-personal-assistant`.
2. Deploy the Docker service.
3. Generate a Railway public domain.
4. Add a Railway Volume to the service and set its mount path to **`/app/storage`**. Railway documents that the mount path must match the application path for relative/local data to persist.
5. Add the secret variable `GEMINI_API_KEY` in Railway Variables. Do not commit the real key.
6. Optional: set `GEMINI_MODEL`.
7. Every push to `main` can trigger a new deployment when Railway's GitHub auto-deploy is enabled.

The `railway.json` file defines Docker build, health check and restart policy. The persistent Volume is a Railway resource and should be attached to the service; it is not created by the Docker build.

## Hugging Face Spaces

The root README contains Hugging Face Docker Space metadata. HF Docker Spaces can run FastAPI and custom Docker applications, with the exposed port configured by `app_port`.

For a Space, create a Docker Space and synchronize this GitHub repository to it. Each new commit to the Space repository triggers a rebuild/restart.

For automated GitHub → Hugging Face synchronization, add a GitHub repository secret named `HF_TOKEN`, then enable the included `.github/workflows/sync-to-huggingface.yml` workflow and replace the placeholder Space ID with your actual Hugging Face Space. The official `huggingface/hub-sync` action supports this workflow.

HF Spaces storage should not be treated as the authoritative store for personal Excel/backup data. Use Railway Volume or an external object store/database for durable application data.

## Gemini

The backend prefers the `GEMINI_API_KEY` environment secret. The Admin page can still store a key in `storage/config.json` for local/personal use. GET /api/settings always masks the configured key.

## API

- GET `/api/health`
- GET `/api/usage`
- GET/POST `/api/settings`
- POST `/api/scrape`
- GET `/api/logs`
- POST `/api/chat`
- GET `/api/excel`
- GET `/api/download-excel/{file_name}`
- GET `/api/download-pdf`
- GET `/api/download-pdf?file_name=example.xlsx`
- POST `/api/backup`

## Data scraper behavior

The built-in collectors use public Google, Bing and DuckDuckGo search pages. They store a fetch diagnostic rather than pretending to bypass authentication, CAPTCHAs, paywalls or private content.

## Security

This is intentionally a single-user application. Before exposing it to untrusted users, add authentication/authorization, strict CORS, rate limiting, CSRF protection where applicable, secret management and audit logging.

Never commit a real Gemini API key. Use Railway/HF secrets for cloud deployments.
