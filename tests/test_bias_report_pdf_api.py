"""GET /bias-reports/{user_id}/{dataset_id}/pdf with the stored-report fixtures."""
import io
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.api import bias_reports
from app.models.bias_report import BiasReportResponse
from app.models.transformation_report import TransformationReportResponse

FX = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FX / name).read_text(encoding="utf-8"))


def _client(monkeypatch, bias: BiasReportResponse, transformation: TransformationReportResponse) -> TestClient:
    async def fake_get_report(user_id, dataset_id, version=None):
        if dataset_id == "missing":
            return None
        return bias

    async def fake_get_transformation(user_id, dataset_id, version):
        assert version == "v3"
        return transformation

    monkeypatch.setattr(bias_reports.bias_report_service, "get_report", fake_get_report)
    monkeypatch.setattr(bias_reports.transformation_report_service, "get_report", fake_get_transformation)
    app = FastAPI()
    app.include_router(bias_reports.router)
    return TestClient(app)


def test_pdf_endpoint_returns_pdf(monkeypatch):
    bias = BiasReportResponse(**_load("bias_report_v2.json"))
    transformation = TransformationReportResponse(**_load("transformation_report_v3.json"))
    client = _client(monkeypatch, bias, transformation)

    response = client.get(f"/bias-reports/{bias.user_id}/{bias.dataset_id}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content[:5] == b"%PDF-"
    assert len(PdfReader(io.BytesIO(response.content)).pages) == 9
    assert "inline" in response.headers["content-disposition"]


def test_pdf_endpoint_missing_report_is_404(monkeypatch):
    bias = BiasReportResponse(**_load("bias_report_v2.json"))
    transformation = TransformationReportResponse(**_load("transformation_report_v3.json"))
    client = _client(monkeypatch, bias, transformation)

    response = client.get("/bias-reports/user-1/missing/pdf")
    assert response.status_code == 404
    assert "Bias report not found" in response.json()["detail"]


def test_pdf_endpoint_unknown_timezone_is_400(monkeypatch):
    bias = BiasReportResponse(**_load("bias_report_v2.json"))
    transformation = TransformationReportResponse(**_load("transformation_report_v3.json"))
    client = _client(monkeypatch, bias, transformation)

    response = client.get(
        f"/bias-reports/{bias.user_id}/{bias.dataset_id}/pdf",
        params={"tz": "Not/AZone"},
    )
    assert response.status_code == 400
    assert "Unknown timezone" in response.json()["detail"]
