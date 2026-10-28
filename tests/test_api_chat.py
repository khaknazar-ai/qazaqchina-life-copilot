from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_chat_passport_query_routes_to_emergency() -> None:
    response = client.post("/api/chat", json={"user_message": "I lost my passport in Beijing"})

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"]
    assert body["scenario"] == "emergency"
    assert body["risk_level"] == "emergency"
    assert body["metadata"]["graph_runtime"] == "local_guidance"
    assert body["grounded_answer"]["language"] == "ru"
    assert body["grounded_answer"]["recommended_steps"]
    assert "Phase 5" not in body["answer"]


def test_chat_work_tourist_query_routes_to_work_status_sensitive() -> None:
    response = client.post(
        "/api/chat",
        json={"user_message": "Can I work on a tourist visa and fix documents later?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scenario"] == "work"
    assert body["risk_level"] == "work_status_sensitive"
    assert body["escalation_required"] is True
