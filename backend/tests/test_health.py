from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health_returns_successful_json() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "teddy"}


def test_homepage_serves_the_upload_screen() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Teddy – Smart AI Analyst" in response.text
