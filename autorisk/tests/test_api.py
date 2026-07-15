from fastapi.testclient import TestClient
from uuid import uuid4

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
    assert "智能風控審核" in response.text


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


def test_conclusion_download_and_ok_feedback() -> None:
    request_id = f"conclusion-{uuid4()}"
    response = client.post(
        "/api/v1/risk-evals/assess",
        headers={"X-API-Key": "autorisk-dev-key"},
        json={
            "request_id": request_id,
            "trigger_source": "PRE_TRADE",
            "fund_code": "FUND-CONCLUSION",
            "fund_name": "Conclusion Fund",
            "indicators": {
                "leverage_ratio": 1.0,
                "single_stock_concentration": 0.05,
                "var_95_1d": 0.01,
                "liquidity_ratio": 0.30,
            },
        },
    )
    assert response.status_code == 201
    report = response.json()

    conclusion_response = client.get(
        f"/api/v1/risk-evals/reports/{report['report_id']}/conclusion",
        headers={"X-API-Key": "autorisk-dev-key"},
    )
    assert conclusion_response.status_code == 200
    conclusion = conclusion_response.json()
    assert conclusion["document_type"] == "AUTORISK_AI_RISK_CONCLUSION"
    assert conclusion["directive"]["headline"] == "准予執行"
    assert conclusion["execution_decision"] == "ALLOW"
    assert len(conclusion["verification"]["certificate_hash"]) == 64

    download_response = client.get(
        f"/api/v1/risk-evals/reports/{report['report_id']}/conclusion/download?format=json",
        headers={"X-API-Key": "autorisk-dev-key"},
    )
    assert download_response.status_code == 200
    assert "attachment" in download_response.headers["content-disposition"]
    assert download_response.json()["certificate_id"] == conclusion["certificate_id"]

    feedback = {
        "idempotency_key": f"ack-{uuid4()}",
        "status": "OK",
        "actor_id": "test-oms",
        "observed_report_hash": report["content_hash"],
        "observed_decision": report["execution_decision"],
        "message": "已按結論處理",
    }
    feedback_response = client.post(
        f"/api/v1/risk-evals/reports/{report['report_id']}/feedback",
        headers={"X-API-Key": "autorisk-dev-key"},
        json=feedback,
    )
    assert feedback_response.status_code == 200
    receipt = feedback_response.json()
    assert receipt["status"] == "OK"
    assert receipt["accepted"] is True
    assert len(receipt["receipt_hash"]) == 64

    duplicate_response = client.post(
        f"/api/v1/risk-evals/reports/{report['report_id']}/feedback",
        headers={"X-API-Key": "autorisk-dev-key"},
        json=feedback,
    )
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["receipt_id"] == receipt["receipt_id"]

    receipt_download = client.get(
        f"/api/v1/risk-evals/reports/{report['report_id']}/feedback/{feedback['idempotency_key']}/download",
        headers={"X-API-Key": "autorisk-dev-key"},
    )
    assert receipt_download.status_code == 200
    assert "attachment" in receipt_download.headers["content-disposition"]
    assert receipt_download.json()["receipt_hash"] == receipt["receipt_hash"]

    verify_response = client.get(
        f"/api/v1/risk-evals/reports/{report['report_id']}/verify",
        headers={"X-API-Key": "autorisk-dev-key"},
    )
    assert verify_response.status_code == 200
    verification = verify_response.json()
    assert verification["content_hash_valid"] is True
    assert len(verification["artifacts"]) == 5
    assert all(item["valid"] for item in verification["artifacts"])

    invalid_feedback = {**feedback, "idempotency_key": f"bad-{uuid4()}", "observed_report_hash": "0" * 64}
    invalid_response = client.post(
        f"/api/v1/risk-evals/reports/{report['report_id']}/feedback",
        headers={"X-API-Key": "autorisk-dev-key"},
        json=invalid_feedback,
    )
    assert invalid_response.status_code == 409
