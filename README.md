# Modular AI Ecosystem

Standalone three-layer AI ecosystem.

- Page 1: Management & Profile Center (3 profiles)
- Page 2: Centralized Modular Dashboard
- Layer 1: AI engine, providers, training and management
- Layer 2: brain, database, memory and knowledge; no chat UI
- Layer 3: agents, bots, operations, user chat and controlled testing/integration bridge

Run:
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000

The main-project bridge is disabled by default and initial tests are read-only.
