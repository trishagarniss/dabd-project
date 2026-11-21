"""Serving-layer tests: 10+ endpoints, RBAC, audit, inference (F-10, F-12, F-16)."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from src.serving.api import app

VIEWER = {"x-api-key": "demo-viewer-key"}
OPERATOR = {"x-api-key": "demo-operator-key"}

GET_ENDPOINTS = [
    "/api/v1/health",
    "/api/v1/flights/active?limit=2",
    "/api/v1/airports/{code}",
    "/api/v1/marts/airspace-density",
    "/api/v1/marts/airport-dimension?limit=2",
    "/api/v1/flights/by-date?date=2024-01-01&limit=2",
    "/api/v1/flights/date-range?start=2024-01-01&end=2024-01-07&limit=2",
    "/api/v1/quality/report",
    "/api/v1/lineage/runs",
    "/api/v1/ml/experiments",
    "/api/v1/ml/predictions?limit=2",
    "/api/v1/metrics",
]

PREDICTION = {
    "input_record_id": "unit-api-001",
    "distance_km": 820.5,
    "hour_of_day": 14,
    "day_of_week": 2,
    "month": 1,
    "dep_delay_min": 5.0,
    "taxi_out_min": 18.0,
    "crs_elapsed_min": 140.0,
}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_at_least_ten_queryable_endpoints(client):
    assert len(GET_ENDPOINTS) >= 10
    paths = {route.path for route in app.routes}
    for endpoint in GET_ENDPOINTS:
        assert endpoint.split("?")[0] in paths
        request_url = endpoint.replace("{code}", "KPBI")
        response = client.get(request_url, headers=VIEWER)
        assert response.status_code == 200, endpoint


def test_date_range_reconciles_with_single_date(client):
    single = client.get("/api/v1/flights/by-date?date=2024-01-01&limit=500", headers=VIEWER).json()
    ranged = client.get(
        "/api/v1/flights/date-range?start=2024-01-01&end=2024-01-01&limit=500",
        headers=VIEWER,
    ).json()
    assert ranged["count"] == single["count"]


def test_missing_api_key_is_401(client):
    assert client.get("/api/v1/flights/active").status_code == 401


def test_invalid_api_key_is_401(client):
    response = client.get("/api/v1/flights/active", headers={"x-api-key": "wrong"})
    assert response.status_code == 401


def test_viewer_cannot_invoke_ml_prediction(client):
    response = client.post("/api/v1/ml/predict-delay", json=PREDICTION, headers=VIEWER)
    assert response.status_code == 403


def test_operator_can_invoke_ml_prediction(client):
    response = client.post("/api/v1/ml/predict-delay", json=PREDICTION, headers=OPERATOR)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["input_record_id"] == PREDICTION["input_record_id"]
    assert body["model_version"]


def test_prediction_input_validation(client):
    bad = {**PREDICTION, "hour_of_day": 99}
    assert client.post("/api/v1/ml/predict-delay", json=bad, headers=OPERATOR).status_code == 422


def test_openapi_documents_all_endpoints(client):
    spec = client.get("/openapi.json").json()
    assert len(spec["paths"]) >= 12


def test_audit_log_records_requests(client):
    from src.common.config import AUDIT_LOG
    from src.common.storage import read_jsonl

    client.get("/api/v1/flights/active", headers=VIEWER)
    rows = read_jsonl(AUDIT_LOG)
    assert rows
    assert any(r.get("endpoint") == "/api/v1/flights/active" for r in rows[-25:])
