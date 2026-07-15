from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_is_public() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "AutoRisk"


def test_business_api_requires_key() -> None:
    response = client.get("/api/v1/risk-evals/rules")
    assert response.status_code == 401


def test_rules_available_with_key() -> None:
    response = client.get(
        "/api/v1/risk-evals/rules",
        headers={"X-API-Key": "autorisk-dev-key"},
    )
    assert response.status_code == 200
    assert response.json()["count"] >= 4


def test_demo_page_is_public() -> None:
    response = client.get("/demo")
    assert response.status_code == 200
    assert "加倉風險評估" in response.text


def test_demo_assessment_runs_full_ai_workflow() -> None:
    response = client.post(
        "/api/v1/risk-evals/demo/assess",
        headers={"X-API-Key": "autorisk-dev-key"},
        json={
            "fund_name": "API Demo Fund",
            "evaluation_date": "2026-07-15",
            "add_amount_hkd": 5_000_000,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["calculation"]["metrics"]["ytd_return"] is not None
    assert payload["calculation"]["metrics"]["max_drawdown"] is not None
    assert payload["calculation"]["metrics"]["var_95_1d"] >= 0
    assert len(payload["calculation"]["nav_history"]) >= 20
    assert len(payload["report"]["ai_reviews"]) == 2
    assert payload["report"]["proposed_trade"]["action"] == "ADD_POSITION"
