"""
Run an Aequitas group audit on labels, scores, and protected attributes.

Aequitas does not load or inspect a model. It compares binary predictions
across groups. Callers supply the evaluation table.
"""
from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd


def _same_label(value: Any, positive: Any) -> bool:
    if pd.isna(value):
        return False
    if value == positive:
        return True
    try:
        if math.isfinite(float(value)) and math.isfinite(float(positive)):
            return float(value) == float(positive)
    except (TypeError, ValueError):
        pass
    return str(value) == str(positive)


def binarize_labels(labels: pd.Series, positive_label: Any) -> tuple[pd.Series, str, list[str]]:
    """
    Map a label column to 0/1 for Aequitas.

    Two classes require ``positive_label`` unless the values are already 0 and 1.
    More than two classes become one-versus-rest around ``positive_label``.
    """
    notes: list[str] = []
    present = labels.dropna()
    n_classes = int(present.nunique())
    if n_classes < 2:
        raise ValueError("Label column has fewer than 2 classes, so a model audit has nothing to compare.")

    numeric_binary = False
    try:
        as_num = pd.to_numeric(present, errors="coerce")
        if as_num.notna().all() and set(as_num.round(6).unique()).issubset({0.0, 1.0}):
            numeric_binary = True
    except (TypeError, ValueError):
        numeric_binary = False

    if positive_label is None:
        if numeric_binary and n_classes == 2:
            binary = pd.to_numeric(labels, errors="coerce").fillna(0).astype(int).clip(0, 1)
            return binary, "binary", notes
        raise ValueError(
            "Aequitas needs a binary positive class. Pass positive_label "
            "(the dataset bias report's pos_label is used when it exists)."
        )

    matched = labels.map(lambda value: _same_label(value, positive_label))
    if int(matched.sum()) == 0:
        raise ValueError(f"positive_label {positive_label!r} does not appear in the label column.")

    binary = matched.astype(int)
    if n_classes > 2:
        notes.append(
            f"The label has {n_classes} classes. Aequitas audits one positive class, "
            f"so '{positive_label}' is 1 and every other label is 0."
        )
        return binary, "one_vs_rest", notes
    return binary, "binary", notes


def reference_groups_for(
    frame: pd.DataFrame,
    protected_attributes: list[str],
    privileged_groups: dict[str, Any] | None,
) -> tuple[dict[str, str], list[str]]:
    """Use the dataset-bias privileged group when it is present, otherwise the majority group."""
    notes: list[str] = []
    privileged = privileged_groups or {}
    chosen: dict[str, str] = {}
    for attr in protected_attributes:
        values = frame[attr].astype(str)
        counts = values.value_counts()
        majority = str(counts.idxmax())
        wanted = privileged.get(attr)
        if wanted is not None and str(wanted) in set(values):
            chosen[attr] = str(wanted)
        else:
            chosen[attr] = majority
            if wanted is not None:
                notes.append(
                    f"Privileged group '{wanted}' for '{attr}' is not in this evaluation table. "
                    f"Disparities use the majority group '{majority}'."
                )
            else:
                notes.append(
                    f"No privileged group was stored for '{attr}'. Disparities use the majority group '{majority}'."
                )
    return chosen, notes


def _records(frame: pd.DataFrame) -> list[dict]:
    table = frame.reset_index()
    payload = json.loads(table.to_json(orient="records"))
    return payload


def run_aequitas_audit(
    frame: pd.DataFrame,
    *,
    protected_attributes: list[str],
    privileged_groups: dict[str, Any] | None = None,
    positive_label: Any = None,
    score_threshold: float = 0.5,
) -> dict[str, Any]:
    """
    Audit ``frame`` columns ``label_value`` (raw labels) and ``score`` (probability or 0/1).

    Protected-attribute columns must already be on ``frame``. Returns JSON records for
    group metrics, disparities (including significance when Aequitas can compute it),
    and overall performance.
    """
    if not protected_attributes:
        raise ValueError(
            "No protected attributes. Run the dataset bias check first, or pass protected_attributes."
        )
    missing = [name for name in protected_attributes if name not in frame.columns]
    if missing:
        raise ValueError(f"Protected attributes are not columns in the evaluation table: {missing}")
    for column in ("label_value", "score"):
        if column not in frame.columns:
            raise ValueError(f"Evaluation table is missing '{column}'.")

    work = frame.dropna(subset=["label_value", "score", *protected_attributes]).copy()
    if work.empty:
        raise ValueError("No rows remain after dropping missing labels, scores, or protected attributes.")

    binary, label_mode, notes = binarize_labels(work["label_value"], positive_label)
    work["label_value"] = binary
    for attr in protected_attributes:
        work[attr] = work[attr].astype(str)
    reference, ref_notes = reference_groups_for(work, protected_attributes, privileged_groups)
    notes.extend(ref_notes)

    scores = pd.to_numeric(work["score"], errors="coerce")
    if scores.isna().any():
        raise ValueError("Score column must be numeric (a probability or a 0/1 prediction).")
    work["score"] = scores

    already_hard = set(work["score"].round(6).unique()).issubset({0.0, 1.0})
    threshold = None if already_hard else {"threshold_type": "fixed", "threshold_value": float(score_threshold)}
    if already_hard:
        notes.append("Scores are already 0/1, so the probability threshold is not applied.")
    else:
        notes.append(f"Probabilities are turned into predictions at {score_threshold}.")

    from aequitas import Audit

    audit_frame = work[["label_value", "score", *protected_attributes]]
    audit = Audit(
        audit_frame,
        threshold=threshold,
        score_column="score",
        label_column="label_value",
        sensitive_attribute_column=protected_attributes,
        reference_groups=reference,
    )
    try:
        audit.audit(bias_args={"check_significance": True, "alpha": 0.05})
    except Exception as exc:
        notes.append(f"Statistical significance was skipped ({exc}).")
        audit.audit(bias_args={"check_significance": False})

    performance = audit.performance()
    return {
        "label_mode": label_mode,
        "positive_label": None if positive_label is None else str(positive_label),
        "protected_attributes": list(protected_attributes),
        "reference_groups": reference,
        "n_rows": int(len(work)),
        "metrics": _records(audit.metrics),
        "disparities": _records(audit.disparities),
        "performance": _records(performance),
        "notes": notes,
    }
