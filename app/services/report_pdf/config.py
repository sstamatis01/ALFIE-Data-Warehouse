"""All tunables in one place: thresholds (fallbacks when the JSON does not carry them),
severity mapping, step-status mapping, palette and timezone."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Tuple

# Okabe-Ito based, colour-blind safe. Severity colour is ALWAYS paired with an icon + word.
PALETTE = dict(
    ok="#009E73", warn="#E69F00", warn_text="#8A5A00", high="#D55E00", info="#0072B2",
    c0="#9DB4C8", c1="#2F4B7C", ink="#1B1F27", mut="#5B6472", grid="#E3E6EA",
    band="#DDF1E9", na="#B8BEC6",
)

SEVERITY_STYLE = {
    #  key      label           icon  colour            background
    "high":   ("High",          "✕", PALETTE["high"], "#FBE7DC"),
    "medium": ("Medium",        "▲", PALETTE["warn"], "#FDF1D8"),
    "notice": ("Notice",        "i", PALETTE["info"], "#E1EEF8"),
    "ok":     ("OK",            "✓", PALETTE["ok"],   "#DFF3EC"),
    "na":     ("Not computed",  "?", PALETTE["na"],   "#EEF0F2"),
}


@dataclass
class ReportConfig:
    # ---- severity per alert kind (PROPOSAL; AutoDW alerts are plain strings without severity) ----
    severity_by_kind: Dict[str, str] = field(default_factory=lambda: {
        "disparate_impact": "high",
        "statistical_parity": "high",
        "representation": "medium",
        "class_imbalance": "medium",
        "other": "medium",
    })
    # ---- fallback thresholds (used only when the JSON does not provide them) ----
    di_band: Tuple[float, float] = (0.8, 1.25)
    spd_abs: float = 0.1
    representation_ratio: float = 3.0
    small_group_n: int = 30
    outlier_notice_pct: float = 5.0
    skew_notice_abs: float = 1.0
    # ---- transformation step status ----
    step_status: Dict[str, str] = field(default_factory=lambda: {
        "missing_value_fill": "applied", "duplicate_removal": "applied", "encoding": "applied",
        "skew_correction": "applied", "drift_mitigation": "applied", "oversampling": "applied",
        "encoding_skipped": "skipped", "oversampling_skipped": "skipped", "task_inference": "info",
    })
    step_names: Dict[str, str] = field(default_factory=lambda: {
        "missing_value_fill": "Fill missing values", "duplicate_removal": "Remove duplicates",
        "encoding": "Encode categories", "encoding_skipped": "Encoding skipped",
        "task_inference": "Detect task type", "skew_correction": "Correct skew",
        "oversampling": "Oversampling (SMOTE)", "oversampling_skipped": "Oversampling (SMOTE)",
        "drift_mitigation": "Scale features (drift)",
    })
    # Step types that count as addressing a *fairness* alert (none exist in AutoDW today).
    fairness_step_types: Tuple[str, ...] = ("reweighing", "fairness_resampling", "group_oversampling")
    # ---- model bias (Aequitas) section ----
    model_footer_text: str = "AutoDW · Model bias report"
    # Fallback band for disparity ratios; the audit alerts carry "outside [0.8, 1.25]" and win when present.
    model_fair_band: Tuple[float, float] = (0.8, 1.25)
    model_min_group: int = 30          # same as model_bias_alerts.MIN_GROUP
    model_pprev_min_gap: float = 0.1   # same as model_bias_alerts.PPREV_GAP (absolute selection-rate gap)
    # Metrics that raise a High alert when outside the band (mirrors model_bias_alerts._RATE_LABELS).
    model_alert_metrics: Tuple[str, ...] = ("pprev", "tpr", "fpr")
    # Rows of the pass/fail matrix (ppr is left out on purpose: it mostly reflects group size).
    model_matrix_metrics: Tuple[str, ...] = ("pprev", "tpr", "fpr", "fnr", "tnr", "precision", "fdr", "for", "npv")
    model_alert_severity: Dict[str, str] = field(default_factory=lambda: {
        "rate": "high",            # "<group> <rate> X times <ref>, outside [...]"
        "small_groups": "medium",  # "... fewer than 30 test rows ..."
        "other": "medium",
    })
    timezone: str = "UTC"           # e.g. "Europe/Bucharest"; set from settings/env in the app
    show_source_paths: bool = True  # the small grey "Data: <json path>" lines under charts
    footer_text: str = "AutoDW · Bias & transformation report"


# Plain-language names for Aequitas group metrics. "kind" says which direction hurts the group:
#   error   -> a higher value than the reference group is worse for the group
#   benefit -> a lower value is worse
#   neutral -> direction depends on whether the positive label is good or bad for people (unknown)
MODEL_METRICS = {
    "pprev": ("Selection rate", "neutral", "Share of the group the model predicts as positive (label = 1)."),
    "tpr": ("True-positive rate", "benefit", "Of the rows that really are positive, how many the model catches."),
    "fpr": ("False-positive rate", "error", "Of the rows that really are negative, how many the model wrongly calls positive."),
    "fnr": ("False-negative rate", "error", "Of the rows that really are positive, how many the model misses."),
    "tnr": ("True-negative rate", "benefit", "Of the rows that really are negative, how many the model correctly calls negative."),
    "precision": ("Precision", "benefit", "Of the rows predicted positive, how many really are positive."),
    "fdr": ("False discovery rate", "error", "Of the rows predicted positive, how many are actually negative."),
    "for": ("False omission rate", "error", "Of the rows predicted negative, how many are actually positive."),
    "npv": ("Negative predictive value", "benefit", "Of the rows predicted negative, how many really are negative."),
    "ppr": ("Share of all positive predictions", "neutral", "The group's share of every positive prediction; mostly reflects group size."),
    "accuracy": ("Accuracy", "benefit", "Share of the group's rows the model gets right."),
    "prev": ("Actual positive rate", "neutral", "Share of the group whose true label is positive (from the test data, not the model)."),
}
