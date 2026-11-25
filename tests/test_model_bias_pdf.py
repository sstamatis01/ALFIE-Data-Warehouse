"""Model bias (Aequitas audit) section of report_pdf: context rules + standalone and merged PDFs."""
import copy
import io
import json
from pathlib import Path

from pypdf import PdfReader

from app.services.model_bias_alerts import build_model_bias_alerts
from app.services.report_pdf import ReportConfig, build_model_bias_html, build_model_bias_pdf, build_report_pdf
from app.services.report_pdf.model_bias_context import build_model_bias_context

FX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def _text(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def test_context_matches_stored_alerts():
    audit = _load("model_bias_report_v1.json")
    ctx = build_model_bias_context(audit)
    assert ctx["band"] == (0.8, 1.25)
    assert ctx["status"]["level"] == "high"
    assert [n for _, n in ctx["status"]["counts"]][:2] == [4, 1]       # 4 rate alerts + 1 small-group caution
    high = sorted((a["name"], g, m) for a in ctx["attributes"] for g, m, _ in a["high_cells"])
    assert high == [("ethnicity", "Indian", "fpr"), ("ethnicity", "Indian", "pprev"),
                    ("ethnicity", "Middle Eastern", "pprev"), ("gender", "Female", "fpr")]
    eth = next(a for a in ctx["attributes"] if a["name"] == "ethnicity")
    assert dict(eth["small"]) == {"African": 10, "Asian": 22, "Other": 11, "Unknown": 5}
    assert eth["groups"][0] == "Caucasian"                              # reference first


def test_context_agrees_with_alert_service():
    """The PDF's High cells must be exactly what model_bias_alerts would raise for the same report."""
    audit = _load("model_bias_report_v1.json")
    rep = audit["report"]
    alerts = build_model_bias_alerts(rep["metrics"], rep["disparities"], audit["reference_groups"], rep["performance"])
    assert alerts == audit["alerts"]                                    # fixture is consistent with the service
    ctx = build_model_bias_context(audit)
    n_rate = sum("outside [" in a for a in alerts)
    assert n_rate == sum(len(a["high_cells"]) for a in ctx["attributes"])


def test_inner_report_only_and_missing_fields():
    audit = _load("model_bias_report_v1.json")
    ctx = build_model_bias_context(audit["report"])                     # no metadata at all
    assert ctx["available"] and ctx["meta"]["model_id"] == "—"
    assert {a["ref"] for a in ctx["attributes"]} == {"Caucasian", "Male"}   # refs inferred from disparities == 1
    empty = build_model_bias_context({"report": {"metrics": [], "disparities": [], "performance": []}})
    assert not empty["available"]
    html = build_model_bias_html({"report": {"metrics": []}})
    assert "not available" in html


def test_no_alerts_gives_ok_banner():
    audit = copy.deepcopy(_load("model_bias_report_v1.json"))
    audit["alerts"] = []
    audit["report"]["alerts"] = []
    for d in audit["report"]["disparities"]:
        for k in list(d):
            if k.endswith("_disparity"):
                d[k] = 1.0
    ctx = build_model_bias_context(audit)
    assert ctx["status"]["level"] == "ok"
    assert all(not a["high_cells"] for a in ctx["attributes"])


def test_standalone_pdf():
    audit = _load("model_bias_report_v1.json")
    bias = _load("bias_report_v2.json")
    pdf = build_model_bias_pdf(audit, bias, config=ReportConfig(timezone="Europe/Bucharest"))
    assert pdf[:5] == b"%PDF-"
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 7
    text = _text(pdf)
    for s in ("Model bias check", "Alerts, in plain language", "Link to the dataset bias findings",
              "Persists in model", "All fairness checks at a glance", "UTC+2", "Indian"):
        assert s in text, s


def test_merged_pdf_includes_model_section():
    bias = _load("bias_report_v2.json")
    tr = _load("transformation_report_v3.json")
    audit = _load("model_bias_report_v1.json")
    base = len(PdfReader(io.BytesIO(build_report_pdf(bias, tr))).pages)
    merged = build_report_pdf(bias, tr, model_bias=audit)
    assert len(PdfReader(io.BytesIO(merged)).pages) == base + 7
    assert "Model bias check" in _text(merged)
