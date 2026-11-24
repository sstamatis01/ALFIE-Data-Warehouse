"""Golden-fixture tests for the AutoDW report PDF. Run: pytest -q tests/test_report_pdf.py"""
import copy, io, json
from pathlib import Path
import pytest
from pypdf import PdfReader
from app.services.report_pdf import build_report_pdf, build_report_html, ReportConfig
from app.services.report_pdf.context import build_context, fmt_value

FX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def bias():
    return json.loads((FX / "bias_report_v2.json").read_text())


@pytest.fixture(scope="module")
def transformation():
    return json.loads((FX / "transformation_report_v3.json").read_text())


def _text(pdf: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


def _pages(pdf: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf)).pages)


def test_merged_pdf_renders(bias, transformation):
    pdf = build_report_pdf(bias, transformation)
    assert pdf[:5] == b"%PDF-"
    assert _pages(pdf) == 9
    txt = _text(pdf)
    for s in ["Bias report", "Transformation report", "Needs attention", "ethnicity",
              "27.067", "1.691", "+0.245", "Disparate impact", "18 steps logged",
              "614", "700", "5 missing", "0.3287"]:
        assert s in txt, s
    # rendering bugs from the old UI must not come back
    assert "[object Object]" not in txt


def test_bias_only_pdf(bias):
    pdf = build_report_pdf(bias, None)
    txt = _text(pdf)
    assert "Bias report" in txt
    assert "Transformation report: not available" in txt   # mitigation_performed but no report
    assert _pages(pdf) == 7


def test_bias_only_without_mitigation(bias):
    b = copy.deepcopy(bias)
    b["report"].pop("mitigation")
    pdf = build_report_pdf(b, None)
    assert _pages(pdf) == 6
    assert "Transformation report" not in _text(pdf)


def test_inner_report_and_step_list_accepted(bias, transformation):
    # callers may pass just the inner `report` dict / list of steps
    html = build_report_html(bias["report"], transformation["report"])
    assert "Transformation report" in html


def test_missing_fairness_profile_degrades(bias):
    b = copy.deepcopy(bias)
    del b["report"]["fairness_profile"]
    del b["report"]["class_imbalance"]
    txt = _text(build_report_pdf(b, None))
    assert "not available" in txt
    assert "No bias alerts raised" in txt


def test_minimal_report_does_not_crash():
    pdf = build_report_pdf({"dataset_id": "x", "dataset_version": "v1", "report": {"shape": [10, 2], "columns": ["a", "b"]}})
    assert pdf[:5] == b"%PDF-"


def test_original_missing_values_mapped(bias, transformation):
    ctx = build_context(bias, transformation)
    assert [f["before"] for f in ctx["transformation"]["fills"]][:2] == ["1 missing", "5 missing"]


def test_dict_values_formatted():
    assert fmt_value({"0": 614, "1": 700}) == "0: 614 · 1: 700"
    assert fmt_value(False) == "false"
    assert fmt_value(0.3287447995) == "0.3287"


def test_severity_is_configurable(bias):
    cfg = ReportConfig()
    cfg.severity_by_kind["disparate_impact"] = "medium"
    ctx = build_context(bias, None, cfg)
    assert sum(a["sev"] == "high" for a in ctx["alerts"]) == 1


def test_thresholds_read_from_json(bias):
    ctx = build_context(bias, None)
    assert ctx["di_band"] == (0.8, 1.25) and ctx["spd_thr"] == 0.1 and ctx["rep_thr"] == 3.0
