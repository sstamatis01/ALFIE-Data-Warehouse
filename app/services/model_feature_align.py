"""Match an evaluation table to the columns a stored model was trained on."""
from __future__ import annotations

from typing import Optional

import pandas as pd


def table_has_features(frame: pd.DataFrame, expected: list[str]) -> bool:
    return set(expected).issubset(frame.columns)


def select_scoring_frame(
    candidates: list[tuple[str, pd.DataFrame]],
    expected: list[str],
    preferred_version: Optional[str],
) -> Optional[tuple[str, pd.DataFrame]]:
    """Prefer the requested version when it already has the model's columns."""
    ordered = sorted(candidates, key=lambda item: item[0] != preferred_version)
    for version, frame in ordered:
        if table_has_features(frame, expected):
            return version, frame
    return None


def _dummy_is_selected(value) -> bool:
    if value is True or value == 1:
        return True
    if isinstance(value, str) and value.strip().lower() in {"true", "1"}:
        return True
    return False


def restore_group_columns(frame: pd.DataFrame, attributes: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """
    Rebuild a categorical column from mitigation-style dummies.

    Bias mitigation replaces ``ethnicity`` with ``ethnicity_Caucasian`` and the
    other group columns. Aequitas needs the original name on each row.
    """
    out = frame.copy()
    restored: list[str] = []
    for attribute in attributes:
        if attribute in out.columns:
            continue
        prefix = f"{attribute}_"
        dummies = [column for column in out.columns if column.startswith(prefix)]
        if not dummies:
            continue
        labels = []
        for row in out[dummies].itertuples(index=False, name=None):
            label = None
            for column, value in zip(dummies, row):
                if _dummy_is_selected(value):
                    label = column[len(prefix):]
                    break
            labels.append(label)
        out[attribute] = labels
        restored.append(attribute)
    return out, restored
