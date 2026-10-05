from app.core.config import settings
def layer1_chat(message):
    return {"layer":"Layer 1","provider":settings.ai_provider,
      "response":"Layer 1 received the management instruction. Local adapter response: "+message[:500],
      "actions":["validate","route","log"]}
