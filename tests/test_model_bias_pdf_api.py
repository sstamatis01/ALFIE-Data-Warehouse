"""GET /bias-reports/model-audit/{user_id}/{model_id}/pdf and include_model_bias on the dataset PDF."""
import io
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.api import bias_reports
from app.models.bias_report import BiasReportResponse
from app.models.model_bias import ModelBiasAuditResponse
from app.models.transformation_report import TransformationReportResponse

FX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def _client(monkeypatch):
    audit = ModelBiasAuditResponse(**_load("model_bias_report_v1.json"))
    bias = BiasReportResponse(**_load("bias_report_v2.json"))
    tr = TransformationReportResponse(**_load("transformation_report_v3.json"))

    async def latest(user_id, model_id):
        return audit if model_id == audit.model_id else None

    async def latest_for_dataset(user_id, dataset_id):
        return audit

    async def get_report(user_id, dataset_id, version=None):
        return bias

    async def get_tr(user_id, dataset_id, version):
        return tr

    monkeypatch.setattr(bias_reports.model_bias_service, "get_latest", latest)
    monkeypatch.setattr(bias_reports.model_bias_service, "get_latest_for_dataset", latest_for_dataset, raising=False)
    monkeypatch.setattr(bias_reports.bias_report_service, "get_report", get_report)
    monkeypatch.setattr(bias_reports.transformation_report_service, "get_report", get_tr)
    app = FastAPI()
    app.include_router(bias_reports.router)
    return TestClient(app), audit, bias


def test_model_bias_pdf_endpoint(monkeypatch):
    client, audit, _ = _client(monkeypatch)
    r = client.get(f"/bias-reports/model-audit/{audit.user_id}/{audit.model_id}/pdf?download=true&tz=Europe/Bucharest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert "attachment" in r.headers["content-disposition"]
    assert len(PdfReader(io.BytesIO(r.content)).pages) == 7


def test_model_bias_pdf_404_and_bad_tz(monkeypatch):
    client, audit, _ = _client(monkeypatch)
    assert client.get(f"/bias-reports/model-audit/{audit.user_id}/nope/pdf").status_code == 404
    assert client.get(f"/bias-reports/model-audit/{audit.user_id}/{audit.model_id}/pdf?tz=Mars/Base").status_code == 400


def test_dataset_pdf_with_model_section(monkeypatch):
    client, _, bias = _client(monkeypatch)
    r = client.get(f"/bias-reports/{bias.user_id}/{bias.dataset_id}/pdf?include_model_bias=true")
    assert r.status_code == 200
    assert len(PdfReader(io.BytesIO(r.content)).pages) == 9 + 7
