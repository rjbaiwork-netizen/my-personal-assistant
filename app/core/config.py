import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME","Modular AI Ecosystem")
    app_env: str = os.getenv("APP_ENV","development")
    ai_provider: str = os.getenv("AI_PROVIDER","local")
    integration_enabled: bool = os.getenv("INTEGRATION_ENABLED","false").lower()=="true"

settings=Settings()
