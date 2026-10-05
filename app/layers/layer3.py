from app.db.store import store
def layer3_chat(message):
    if "brain" in message.lower() or "memory" in message.lower():
        store.log("layer3.read",message)
        return {"layer":"Layer 3","response":"Layer 3 can read controlled Brain/Memory capabilities through Layer 2 contracts.","action":"read-only"}
    store.log("layer3.execute",message)
    return {"layer":"Layer 3","response":"Operational request accepted. External side effects require an explicit adapter and permission.","action":"planned"}
