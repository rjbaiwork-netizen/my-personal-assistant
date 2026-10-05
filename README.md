# My Personal Assistant

A single-user Personal AI & Data Scraper Platform built with FastAPI, Pandas/OpenPyXL, vanilla JavaScript and Tailwind CSS.

## Included structure

```
my-personal-assistant/
├── backend/
│   ├── main.py
│   ├── scraper.py
│   ├── ai_assistant.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
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

## Features

- Responsive single-page dashboard.
- Public-page fetch diagnostics for Google, Bing and DuckDuckGo.
- Structured Excel logging with **append** and **new file** modes.
- Gemini API chat and log analysis.
- Settings stored in `storage/config.json`.
- Excel downloads and sanitized ZIP backups.
- Client-side daily activity counter (8-hour reference target).
- Docker and Render deployment configuration.

## Run locally

Requires Python 3.10+.

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 10000
```

Open `http://localhost:10000`.

## Gemini

Configure your Gemini API key through **Admin & Settings**. The settings API masks the stored key when returning configuration data.

The application uses the Gemini REST API. Free-tier availability and quotas depend on the Google AI/Gemini account and model in use; this application does not bypass provider limits.

## Storage

Excel files are written to `storage/excel_files/`. ZIP backups are written to `storage/backups/`. Backups exclude previous backups and redact the Gemini API key.

## Docker

```bash
docker build -t my-personal-assistant .
docker run -p 10000:10000 my-personal-assistant
```

## Render

The included `render.yaml` defines a Docker web service on the free plan. Free/ephemeral instances should not be treated as durable storage, so download or back up important Excel data regularly.

## Security notes

This is intentionally a single-user personal tool, not a multi-tenant SaaS. Do not expose it publicly with sensitive data without adding authentication, HTTPS policy, rate limiting and a proper secrets manager.

Never commit a real Gemini API key to Git.