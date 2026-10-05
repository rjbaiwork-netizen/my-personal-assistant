from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app)
def test_health():
    r=client.get("/api/health"); assert r.status_code==200; assert r.json()["status"]=="ok"
def test_profiles():
    r=client.get("/api/profiles"); assert r.status_code==200; assert len(r.json())==3
def test_layer2_has_no_chat():
    assert client.post("/api/layer2/chat",json={"message":"hello"}).status_code==404
def test_safe_testing():
    r=client.post("/api/testing/run",json={"target":"main-project","mode":"read-only"})
    assert r.status_code==200 and r.json()["status"]=="passed"
