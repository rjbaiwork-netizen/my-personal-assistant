"""Production entrypoint that attaches the isolated AI ecosystem to the legacy app.

The legacy backend/main.py source remains unchanged. This wrapper is the only integration seam.
"""
from .main import app as legacy_app
from .ai_ecosystem.api import router as ai_router

legacy_app.include_router(ai_router)
app = legacy_app
