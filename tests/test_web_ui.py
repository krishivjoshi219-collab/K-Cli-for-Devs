"""
tests/test_web_ui.py - Test Suite for K-CLI World-Class Web UI
"""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from k_cli.web.server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_web_ui_index_endpoint(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "K-CLI" in response.text


def test_web_ui_status_endpoint(client: TestClient):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "active_model" in data
    assert "git_branch" in data
    assert "ram_usage_mb" in data


def test_web_ui_run_agent_endpoint(client: TestClient):
    payload = {
        "prompt": "Write a python factorial function",
        "language": "python",
        "mock": True
    }
    response = client.post("/api/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert "final_code" in data


def test_web_ui_triage_endpoint(client: TestClient):
    log_text = "Traceback (most recent call last):\n  File \"app.py\", line 10, in <module>\nValueError: invalid literal"
    response = client.post("/api/triage", json={"log_text": log_text})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "report" in data


def test_web_ui_conflicts_endpoint(client: TestClient):
    response = client.get("/api/conflicts")
    assert response.status_code == 200
    data = response.json()
    assert "total_conflicts" in data
    assert "conflicts" in data


def test_web_ui_security_scan_endpoint(client: TestClient):
    response = client.get("/api/security/scan")
    assert response.status_code == 200
    data = response.json()
    assert "findings" in data


def test_web_ui_chaos_scan_endpoint(client: TestClient):
    response = client.get("/api/chaos/scan")
    assert response.status_code == 200
    data = response.json()
    assert "total_modules" in data


def test_web_ui_devdocs_search_endpoint(client: TestClient):
    response = client.post("/api/devdocs/search", json={"query": "asyncio.run", "limit": 3})
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


def test_web_ui_models_endpoint(client: TestClient):
    response = client.get("/api/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert len(data["models"]) > 0


def test_web_ui_websocket_agent(client: TestClient):
    with client.websocket_connect("/ws/agent") as websocket:
        websocket.send_json({
            "prompt": "Write a quicksort function in python",
            "language": "python",
            "mock": True
        })
        start_msg = websocket.receive_json()
        assert start_msg["type"] == "start"

        tokens = []
        while True:
            msg = websocket.receive_json()
            if msg["type"] in ("complete", "error"):
                assert msg["type"] == "complete"
                assert msg["success"] is True
                break
            elif msg["type"] == "token":
                tokens.append(msg["token"])

        assert len(tokens) > 0


def test_web_ui_credentials_endpoints(client: TestClient):
    # 1. Get credentials status
    res = client.get("/api/credentials")
    assert res.status_code == 200
    data = res.json()
    assert "statuses" in data


def test_web_ui_monitor_endpoint(client):
    res = client.get("/monitor")
    assert res.status_code == 200
    assert "K-CLI Live Agent Synchronized Second Window" in res.text

    # 2. Save credentials
    save_res = client.post("/api/credentials", json={"key_name": "GROQ_API_KEY", "key_value": "gsk_1234567890abcdef1234567890"})
    assert save_res.status_code == 200
    save_data = save_res.json()
    assert save_data["success"] is True

    # 3. Test key
    test_res = client.post("/api/credentials/test", json={"key_name": "OLLAMA_URL"})
    assert test_res.status_code == 200
    assert "success" in test_res.json()


def test_web_ui_custom_model_registration(client: TestClient):
    payload = {
        "model_id": "ollama/custom-test:7b",
        "description": "Test custom model"
    }
    res = client.post("/api/models/custom", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["model"]["id"] == "ollama/custom-test:7b"

    # Verify default model was set
    def_res = client.get("/api/models/default")
    assert def_res.status_code == 200
    assert def_res.json()["default_model"] == "ollama/custom-test:7b"
