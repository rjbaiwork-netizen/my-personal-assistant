from collections import deque
from datetime import datetime,timezone

class Store:
    def __init__(self):
        self.events=deque(maxlen=100)
        self.brain={"knowledge_items":0,"memories":0,"agents":0,"bots":0,"status":"ready"}
    def log(self,event,detail):
        self.events.appendleft({"event":event,"detail":detail[:240],"timestamp":datetime.now(timezone.utc).isoformat()})
    def dashboard(self):
        return {"timestamp":datetime.now(timezone.utc).isoformat(),"layers":{
            "layer1":{"status":"online","role":"AI engine & management"},
            "layer2":{"status":self.brain["status"],"role":"brain, memory & data"},
            "layer3":{"status":"online","role":"agents, bots, operations & testing"}},
            "brain":self.brain,"recent_activity":list(self.events)[:20]}
    def brain_summary(self):
        return {"layer":"Layer 2","chat":False,**self.brain}
store=Store()
