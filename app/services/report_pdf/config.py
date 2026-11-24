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
    timezone: str = "UTC"           # e.g. "Europe/Bucharest"; set from settings/env in the app
    show_source_paths: bool = True  # the small grey "Data: <json path>" lines under charts
    footer_text: str = "AutoDW · Bias & transformation report"
