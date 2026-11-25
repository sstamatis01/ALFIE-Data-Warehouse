"""Plain-language alerts for an Aequitas model audit."""
from __future__ import annotations

from typing import Any, Optional

FAIR_LOW = 0.8
FAIR_HIGH = 1.25
MIN_GROUP = 30
PPREV_GAP = 0.1

_RATE_LABELS = {
    "pprev": "selection rate",
    "tpr": "true-positive rate",
    "fpr": "false-positive rate",
}


def _as_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _join_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + ", and " + names[-1]


def _predicted_positive_count(performance: list[dict]) -> Optional[float]:
    for row in performance:
        if row.get("attribute_value") == "all" or row.get("attribute_name") == "group_performance":
            count = _as_float(row.get("pp"))
            if count is not None:
                return count
    return None


def _group_sizes(metrics: list[dict], performance: list[dict]) -> dict[tuple[str, str], int]:
    """Derive each group's row count from its share of the positive predictions."""
    predicted = _predicted_positive_count(performance)
    sizes: dict[tuple[str, str], int] = {}
    if predicted is None:
        return sizes
    for row in metrics:
        ppr = _as_float(row.get("ppr"))
        pprev = _as_float(row.get("pprev"))
        attr = row.get("attribute_name")
        value = row.get("attribute_value")
        if attr is None or value is None or ppr is None or pprev is None or pprev == 0:
            continue
        sizes[(str(attr), str(value))] = int(round(predicted * ppr / pprev))
    return sizes


def _outside_band(disparity: Optional[float]) -> bool:
    return disparity is not None and (disparity < FAIR_LOW or disparity > FAIR_HIGH)


def build_model_bias_alerts(
    metrics: list[dict],
    disparities: list[dict],
    reference_groups: dict[str, str],
    performance: list[dict] | None = None,
) -> list[str]:
    """
    Flag selection, true-positive, and false-positive disparities against the reference group.

    A ratio of 1 matches the reference group. The band is the same one the dataset
    fairness report uses for disparate impact. Groups under 30 rows get a caution
    instead of a rate alert. The share of all positive predictions (ppr) is not alerted:
    a small group is a small share even when its selection rate matches.
    """
    performance = performance or []
    sizes = _group_sizes(metrics, performance)
    rates = {
        (str(row.get("attribute_name")), str(row.get("attribute_value"))): row
        for row in metrics
        if row.get("attribute_name") is not None and row.get("attribute_value") is not None
    }
    small: dict[str, list[str]] = {}
    alerts: list[str] = []

    for row in disparities:
        attr = str(row.get("attribute_name") or "")
        group = str(row.get("attribute_value") or "")
        reference = str(reference_groups.get(attr) or "")
        if not attr or not group or group == reference:
            continue
        size = sizes.get((attr, group))
        if size is not None and size < MIN_GROUP:
            small.setdefault(attr, []).append(group)
            continue

        rate_row = rates.get((attr, group), {})
        ref_row = rates.get((attr, reference), {})
        for key, label in _RATE_LABELS.items():
            disparity = _as_float(row.get(f"{key}_disparity"))
            if not _outside_band(disparity):
                continue
            if key == "pprev":
                group_rate = _as_float(rate_row.get("pprev"))
                ref_rate = _as_float(ref_row.get("pprev"))
                if group_rate is None or ref_rate is None or abs(group_rate - ref_rate) < PPREV_GAP:
                    continue
            alerts.append(
                f"{attr}: {group} {label} {disparity:.2f} times {reference}, outside [0.8, 1.25]"
            )

    cautions: list[str] = []
    for attr, groups in small.items():
        listed = _join_names(groups)
        verb = "has" if len(groups) == 1 else "have"
        cautions.append(
            f"{attr}: {listed} {verb} fewer than 30 test rows — treat those ratios cautiously"
        )
    return cautions + alerts


def user_audit_note(
    *,
    n_rows: int,
    eval_split: Optional[str],
    mitigated: bool,
    reference_groups: dict[str, str],
    score_threshold: float,
    hard_scores: bool,
) -> str:
    """One sentence for a platform user. Developer setup details stay out of this text."""
    if mitigated and eval_split:
        sample = f"{n_rows}-row mitigated {eval_split} set"
    elif mitigated:
        sample = f"{n_rows}-row mitigated dataset"
    elif eval_split:
        sample = f"{n_rows}-row {eval_split} set"
    else:
        sample = f"{n_rows}-row dataset"

    pairs = [f"{group} for {attr}" for attr, group in reference_groups.items()]
    if not pairs:
        compared = "the largest group in each protected attribute"
    else:
        compared = _join_names(pairs)
    plural = "groups" if len(reference_groups) != 1 else "group"

    if hard_scores:
        call = "The model scores were already positive or negative calls."
    else:
        call = f"A positive prediction means probability at least {score_threshold:g}."
    return (
        f"The model was checked on the {sample}, with {compared} as the comparison {plural}. {call}"
    )
