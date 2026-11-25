"""Aequitas audit on a small binary prediction table."""
import pandas as pd

from app.services.aequitas_audit import binarize_labels, run_aequitas_audit


def _frame() -> pd.DataFrame:
    # Group A is recovered perfectly. Group B is never predicted positive.
    rows = []
    for _ in range(40):
        rows.append({"label_value": 1, "score": 1, "gender": "a"})
    for _ in range(10):
        rows.append({"label_value": 0, "score": 0, "gender": "a"})
    for _ in range(40):
        rows.append({"label_value": 1, "score": 0, "gender": "b"})
    for _ in range(10):
        rows.append({"label_value": 0, "score": 0, "gender": "b"})
    return pd.DataFrame(rows)


def test_binary_labels_do_not_need_a_positive_class():
    binary, mode, notes = binarize_labels(pd.Series([0, 1, 1, 0]), None)
    assert mode == "binary"
    assert notes == []
    assert list(binary) == [0, 1, 1, 0]


def test_two_string_classes_require_a_positive_label():
    try:
        binarize_labels(pd.Series(["cat", "dog", "cat"]), None)
    except ValueError as exc:
        assert "positive_label" in str(exc)
    else:
        raise AssertionError("expected a positive_label error")


def test_audit_reports_group_disparity():
    result = run_aequitas_audit(
        _frame(),
        protected_attributes=["gender"],
        privileged_groups={"gender": "a"},
    )
    assert result["n_rows"] == 100
    assert result["reference_groups"] == {"gender": "a"}
    metrics = {row["attribute_value"]: row for row in result["metrics"]}
    disparities = {row["attribute_value"]: row for row in result["disparities"]}
    assert metrics["a"]["tpr"] == 1
    assert metrics["b"]["tpr"] == 0
    assert disparities["b"]["tpr_disparity"] == 0
