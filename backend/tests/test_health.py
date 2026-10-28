from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from desk.api.main import app


def test_health_ok() -> None:
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    time_utc = datetime.fromisoformat(body["time_utc"])
    assert time_utc.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - time_utc) < timedelta(minutes=1)


def test_openapi_has_health_operation() -> None:
    schema = app.openapi()
    assert schema["paths"]["/api/health"]["get"]["operationId"] == "getHealth"


def test_cors_allows_llm_key_header() -> None:
    client = TestClient(app)
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-LLM-Key",
        },
    )
    assert response.status_code == 200
    assert "x-llm-key" in response.headers["access-control-allow-headers"].lower()
