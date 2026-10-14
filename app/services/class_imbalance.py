"""
Class-imbalance diagnostics and text-safe train resampling.

Classic SMOTE needs numeric features; raw text columns must use document-level
undersample / oversample instead. Used by the bias-detection consumer.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# Extreme when majority/minority >= this, or minority share below MINORITY_SHARE_ALERT.
IMBALANCE_RATIO_ALERT = 20.0
MINORITY_SHARE_ALERT = 0.01  # 1%

# Hybrid resample defaults (train only).
MAJORITY_CAP_FACTOR = 3.0  # majority <= factor * median class count
MINORITY_FLOOR_FACTOR = 1.0  # each class >= factor * median (after cap logic)
DEFAULT_RANDOM_STATE = 42


def is_text_like_series(s: pd.Series) -> bool:
    if not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
        return False
    non_null = s.dropna()
    if non_null.empty:
        return False
    sample = non_null.astype(str).head(2000)
    avg_len = float(sample.str.len().mean())
    uniq = int(sample.nunique(dropna=True))
    return avg_len >= 20 or uniq >= 50


def detect_text_feature_columns(
    df: pd.DataFrame, target_column: str | None = None
) -> list[str]:
    cols = []
    for c in df.columns:
        if target_column and c == target_column:
            continue
        if is_text_like_series(df[c]):
            cols.append(c)
    return cols


def is_discrete_classification_target(y: pd.Series) -> bool:
    if y is None or y.empty:
        return False
    nunique = int(y.nunique(dropna=True))
    if nunique < 2 or nunique > 50:
        return False
    if pd.api.types.is_object_dtype(y) or pd.api.types.is_categorical_dtype(y):
        return True
    if pd.api.types.is_bool_dtype(y):
        return True
    if pd.api.types.is_integer_dtype(y) or pd.api.types.is_numeric_dtype(y):
        # Heuristic: few unique values relative to rows → classification labels
        return nunique <= min(50, max(2, int(len(y) * 0.05) + 1))
    return False


def build_class_imbalance_profile(
    df: pd.DataFrame,
    target_column: str | None,
    *,
    ratio_alert: float = IMBALANCE_RATIO_ALERT,
    minority_share_alert: float = MINORITY_SHARE_ALERT,
) -> dict[str, Any] | None:
    """
    Per-class counts / shares and extreme-imbalance flag for the bias report.

    Returns None if there is no usable discrete target.
    """
    if not target_column or target_column not in df.columns:
        return None
    y = df[target_column]
    if not is_discrete_classification_target(y):
        return None

    vc = y.value_counts(dropna=False)
    n = int(len(y))
    if n == 0 or vc.empty:
        return None

    counts = {str(k): int(v) for k, v in vc.items()}
    pct = {str(k): round(100.0 * v / n, 4) for k, v in vc.items()}
    max_c = int(vc.max())
    min_c = int(vc.min())
    imbalance_ratio = round(float(max_c / min_c), 4) if min_c > 0 else float("inf")
    minority_share = float(min_c / n) if n else 0.0
    majority_label = str(vc.idxmax())
    minority_label = str(vc.idxmin())

    extreme = bool(
        (min_c > 0 and imbalance_ratio >= ratio_alert)
        or minority_share < minority_share_alert
    )

    text_cols = detect_text_feature_columns(df, target_column)
    modality = "text_classification" if text_cols else "tabular_classification"

    alerts: list[dict[str, Any]] = []
    if extreme:
        alerts.append(
            {
                "type": "extreme_class_imbalance",
                "message": (
                    f"Target '{target_column}' is extremely imbalanced "
                    f"(ratio={imbalance_ratio}:1, minority={minority_label} "
                    f"{pct.get(minority_label, 0):.4f}%). "
                    "Majority-class classifiers and accuracy metrics will mislead; "
                    "use text-safe resampling and macro-F1 / class weights."
                ),
                "imbalance_ratio": imbalance_ratio,
                "minority_share": round(minority_share, 6),
            }
        )
    if text_cols and extreme:
        alerts.append(
            {
                "type": "text_smote_inapplicable",
                "message": (
                    "Classic SMOTE cannot run on raw text features. "
                    "Mitigation uses document-level undersample/oversample on train only."
                ),
                "text_columns": text_cols,
            }
        )

    return {
        "target_column": target_column,
        "modality": modality,
        "n_rows": n,
        "n_classes": int(len(vc)),
        "class_counts": counts,
        "class_percentages": pct,
        "majority_label": majority_label,
        "minority_label": minority_label,
        "imbalance_ratio": imbalance_ratio,
        "minority_share": round(minority_share, 6),
        "extreme_imbalance": extreme,
        "text_feature_columns": text_cols,
        "thresholds": {
            "imbalance_ratio_alert": ratio_alert,
            "minority_share_alert": minority_share_alert,
        },
        "alerts": alerts,
        "fairness_profile_note": (
            "Demographic fairness_profile requires protected-attribute columns; "
            "class imbalance alone is learning bias toward the majority label."
        ),
    }


def resample_text_train_balance(
    df: pd.DataFrame,
    target_column: str,
    *,
    majority_cap_factor: float = MAJORITY_CAP_FACTOR,
    minority_floor_factor: float = MINORITY_FLOOR_FACTOR,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Hybrid document-level balance on a train split:
    - Undersample classes above majority_cap_factor * median class count
    - Oversample (with replacement) classes below minority_floor_factor * median

    Returns (resampled_df, metadata).
    """
    if target_column not in df.columns:
        raise ValueError(f"target_column '{target_column}' not in dataframe")

    y = df[target_column]
    vc = y.value_counts()
    before = {str(k): int(v) for k, v in vc.items()}
    if vc.empty or len(vc) < 2:
        return df.copy(), {
            "method": "text_random_oversample_undersample",
            "skipped": True,
            "reason": "fewer than 2 classes",
            "before": before,
            "after": before,
        }

    median_count = float(np.median(vc.values.astype(float)))
    cap = max(1, int(round(majority_cap_factor * median_count)))
    floor = max(1, int(round(minority_floor_factor * median_count)))
    # Keep floor <= cap so targets are consistent
    floor = min(floor, cap)

    rng = np.random.RandomState(random_state)
    parts: list[pd.DataFrame] = []
    after: dict[str, int] = {}
    actions: dict[str, str] = {}

    for label, count in vc.items():
        subset = df.loc[y == label]
        key = str(label)
        if count > cap:
            idx = rng.choice(subset.index.to_numpy(), size=cap, replace=False)
            sampled = subset.loc[idx]
            actions[key] = f"undersample {count}->{cap}"
        elif count < floor:
            idx = rng.choice(subset.index.to_numpy(), size=floor, replace=True)
            sampled = subset.loc[idx]
            actions[key] = f"oversample {count}->{floor}"
        else:
            sampled = subset
            actions[key] = f"keep {count}"
        parts.append(sampled)
        after[key] = int(len(sampled))

    out = pd.concat(parts, axis=0)
    out = out.sample(frac=1.0, random_state=random_state).reset_index(drop=True)

    meta = {
        "method": "text_random_oversample_undersample",
        "skipped": False,
        "majority_cap_factor": majority_cap_factor,
        "minority_floor_factor": minority_floor_factor,
        "median_class_count": median_count,
        "majority_cap": cap,
        "minority_floor": floor,
        "before": before,
        "after": after,
        "actions": actions,
        "n_rows_before": int(len(df)),
        "n_rows_after": int(len(out)),
        "random_state": random_state,
    }
    return out, meta
