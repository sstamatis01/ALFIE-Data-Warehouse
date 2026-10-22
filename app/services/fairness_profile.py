"""
Dataset-level fairness profile for AutoDW bias reports.

Resolution of protected attributes (priority):
  1. Explicit list from Kafka bias-trigger / API request (user / Agentic Core)
  2. Heuristic regex match on column headers (tabular or vision annotation CSV)
  3. None → omit ``fairness_profile`` (do not invent attributes from the label alone)

Metrics use AIF360 sklearn API when installed; otherwise numpy fallbacks
(same formulas as ``scripts/aif360_bias_report_probe.py``).
"""
from __future__ import annotations

import logging
import math
import re
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import pandas as pd

logger = logging.getLogger(__name__)

# Column-name patterns for sensitive / demographic attributes (human-related).
# Matched case-insensitively against the full header (anchors on word-ish tokens).
PROTECTED_COLUMN_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("sex_gender", re.compile(r"(?i)(^|[_ -])(sex|gender|gend)($|[_ -])")),
    ("ethnicity_race", re.compile(
        r"(?i)(^|[_ -])(ethn(icity)?|race|racial|nationality|origin)($|[_ -])"
    )),
    ("age", re.compile(r"(?i)(^|[_ -])(age|age_group|agegroup|age_bin|agebin)($|[_ -])")),
    ("religion", re.compile(r"(?i)(^|[_ -])(relig(ion)?|faith|creed)($|[_ -])")),
    ("disability", re.compile(r"(?i)(^|[_ -])(disabilit(y|ies)|disabled)($|[_ -])")),
    ("marital", re.compile(r"(?i)(^|[_ -])(marital|married|relationship_status)($|[_ -])")),
    ("pregnancy", re.compile(r"(?i)(^|[_ -])(pregnan(t|cy)|maternity)($|[_ -])")),
    ("sexual_orientation", re.compile(
        r"(?i)(^|[_ -])(sexual_orientation|orientation|lgbtq?)($|[_ -])"
    )),
    ("income_socioeconomic", re.compile(
        r"(?i)(^|[_ -])(income|socio[-_]?economic|ses)($|[_ -])"
    )),
    ("language", re.compile(r"(?i)(^|[_ -])(language|mother_tongue|native_lang)($|[_ -])")),
    ("zip_geo", re.compile(
        r"(?i)(^|[_ -])(zip|zipcode|postal|postcode|neighborhood|neighbourhood)($|[_ -])"
    )),
)

# Prefer these categories when auto-picking a privileged group (mode otherwise).
_PRIVILEGED_VALUE_HINTS = {
    "sex_gender": ("male", "m", "man", "1"),
    "ethnicity_race": ("white", "caucasian", "majority"),
}


def _pct(n: int, total: int) -> Optional[float]:
    if total <= 0:
        return None
    return round(float(n) / float(total), 6)


def _safe_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def detect_protected_attribute_candidates(
    columns: Sequence[Any],
    *,
    exclude: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Heuristic scan of column headers for likely protected attributes.

    Returns a list of ``{column, category, pattern}`` (stable order, de-duplicated).
    """
    exclude_l = {str(x).strip().lower() for x in (exclude or []) if x is not None}
    found: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for col in columns:
        name = str(col)
        name_l = name.strip().lower()
        if not name_l or name_l in exclude_l or name_l in seen:
            continue
        for category, pattern in PROTECTED_COLUMN_PATTERNS:
            if pattern.search(name_l):
                found.append(
                    {
                        "column": name,
                        "category": category,
                        "pattern": pattern.pattern,
                    }
                )
                seen.add(name_l)
                break
    return found


def normalize_protected_attributes_input(
    raw: Any,
) -> Tuple[List[str], Dict[str, str]]:
    """
    Normalize Kafka/API protected_attributes payload.

    Accepts:
      - ``["gender", "ethnicity"]``
      - ``[{"name": "gender", "privileged": "Male"}, ...]``
      - ``{"gender": "Male", "ethnicity": "Caucasian"}``  (name → privileged)
    """
    attrs: List[str] = []
    privileged: Dict[str, str] = {}
    if raw is None:
        return attrs, privileged
    if isinstance(raw, dict):
        for k, v in raw.items():
            name = str(k).strip()
            if not name:
                continue
            attrs.append(name)
            if v is not None and str(v).strip() != "":
                privileged[name] = str(v)
        return attrs, privileged
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("column") or "").strip()
                if not name:
                    continue
                attrs.append(name)
                priv = item.get("privileged") or item.get("privileged_group")
                if priv is not None and str(priv).strip() != "":
                    privileged[name] = str(priv)
            else:
                name = str(item).strip()
                if name:
                    attrs.append(name)
        return attrs, privileged
    name = str(raw).strip()
    if name:
        attrs.append(name)
    return attrs, privileged


def infer_privileged_group(series: pd.Series, *, category: Optional[str] = None) -> Optional[str]:
    """Pick a privileged group: hint match if present, else mode (most frequent)."""
    s = series.dropna().astype(str)
    if s.empty:
        return None
    vc = s.value_counts()
    if category and category in _PRIVILEGED_VALUE_HINTS:
        hints = {h.lower() for h in _PRIVILEGED_VALUE_HINTS[category]}
        for val in vc.index.astype(str):
            if val.strip().lower() in hints:
                return str(val)
    return str(vc.index[0])


def _infer_pos_label(y: pd.Series, explicit: Any = None) -> Any:
    if explicit is not None and str(explicit).strip() != "":
        # Keep numeric if series is numeric-like
        try:
            if pd.api.types.is_numeric_dtype(y):
                return type(y.dropna().iloc[0])(explicit) if len(y.dropna()) else explicit
        except Exception:
            pass
        return explicit
    non_null = y.dropna()
    if non_null.empty:
        return 1
    # Prefer 1 / True / "positive"-ish
    vals = list(non_null.unique())
    for cand in (1, 1.0, True, "1", "true", "True", "yes", "positive", "alert"):
        if cand in vals or str(cand) in [str(v) for v in vals]:
            for v in vals:
                if v == cand or str(v) == str(cand):
                    return v
    # Fallback: most frequent class
    return non_null.value_counts().index[0]


# Cap for treating a target as discrete for fairness crosstabs / AIF360.
# Continuous scores (e.g. 564 unique accessibility_score values) must not expand
# into language × score contingency tables (multi-MB reports that crash agents).
_FAIRNESS_MAX_DISCRETE_CLASSES = 15

# Agent / UI friendly caps for classification fairness payloads.
_FAIRNESS_MAX_GROUPS_PER_ATTR = 10
_FAIRNESS_MAX_INTERSECTION_GROUPS = 20
_FAIRNESS_MAX_PAIRWISE = 8
_FAIRNESS_MAX_GROUPS_UNDER_30 = 8
_FAIRNESS_OTHER_LABEL = "__other__"


def is_discrete_fairness_target(y: pd.Series) -> bool:
    """
    True when target is suitable for classification-style fairness (DI/SPD, crosstabs).

    Continuous / high-cardinality numeric targets return False.
    """
    if y is None or y.empty:
        return False
    try:
        from .class_imbalance import is_discrete_classification_target

        if is_discrete_classification_target(y):
            return True
    except Exception:
        pass
    nunique = int(y.nunique(dropna=True))
    if nunique < 2 or nunique > _FAIRNESS_MAX_DISCRETE_CLASSES:
        return False
    if pd.api.types.is_object_dtype(y) or pd.api.types.is_categorical_dtype(y):
        return True
    if pd.api.types.is_bool_dtype(y):
        return True
    if pd.api.types.is_integer_dtype(y):
        return nunique <= _FAIRNESS_MAX_DISCRETE_CLASSES
    # Floats with few unique values can be ordinal labels; many uniques → continuous
    if pd.api.types.is_numeric_dtype(y):
        return nunique <= min(_FAIRNESS_MAX_DISCRETE_CLASSES, max(2, int(len(y) * 0.05) + 1))
    return False


def _continuous_target_summary(y: pd.Series) -> dict[str, Any]:
    """Compact stats for regression / continuous targets (no per-value counts)."""
    s = pd.to_numeric(y, errors="coerce").dropna()
    out: dict[str, Any] = {
        "n_rows": int(len(y)),
        "n_non_null": int(len(s)),
        "n_unique": int(y.nunique(dropna=True)),
        "kind": "continuous",
    }
    if s.empty:
        return out
    out.update(
        {
            "mean": float(s.mean()),
            "std": float(s.std()) if len(s) > 1 else 0.0,
            "min": float(s.min()),
            "max": float(s.max()),
            "median": float(s.median()),
            "p25": float(s.quantile(0.25)),
            "p75": float(s.quantile(0.75)),
        }
    )
    return out


def _topk_collapse_series(
    series: pd.Series,
    max_groups: int = _FAIRNESS_MAX_GROUPS_PER_ATTR,
    *,
    other_label: str = _FAIRNESS_OTHER_LABEL,
) -> Tuple[pd.Series, dict[str, Any]]:
    """
    Keep the top-``max_groups`` values by frequency; map the rest to ``other_label``.
    Returns (collapsed_series, truncation_meta).
    """
    filled = series.fillna("<NA>").astype(str)
    vc = filled.value_counts(dropna=False)
    n_orig = int(len(vc))
    if n_orig <= max_groups:
        return filled, {
            "truncated": False,
            "n_groups_original": n_orig,
            "n_groups_kept": n_orig,
            "kept_groups": [str(x) for x in vc.index.tolist()],
            "other_count": 0,
        }
    kept = [str(x) for x in vc.head(max_groups).index.tolist()]
    keep_set = set(kept)
    collapsed = filled.where(filled.isin(keep_set), other_label)
    other_count = int((~filled.isin(keep_set)).sum())
    return collapsed, {
        "truncated": True,
        "n_groups_original": n_orig,
        "n_groups_kept": max_groups,
        "kept_groups": kept,
        "other_label": other_label,
        "other_count": other_count,
    }


def representation(
    df: pd.DataFrame,
    col: str,
    *,
    max_groups_under_30: int = _FAIRNESS_MAX_GROUPS_UNDER_30,
) -> dict[str, Any]:
    vc = df[col].fillna("<NA>").astype(str).value_counts(dropna=False)
    total = int(len(df))
    groups = {
        str(k): {"count": int(v), "percent": _pct(int(v), total)}
        for k, v in vc.items()
    }
    counts = [g["count"] for g in groups.values()]
    under_30 = [k for k, g in groups.items() if g["count"] < 30]
    under_30_omitted = max(0, len(under_30) - max_groups_under_30)
    return {
        "groups": groups,
        "n_groups": len(groups),
        "largest_group": max(groups, key=lambda k: groups[k]["count"]) if groups else None,
        "smallest_group": min(groups, key=lambda k: groups[k]["count"]) if groups else None,
        "max_min_ratio": round(max(counts) / max(min(counts), 1), 3) if counts else None,
        "groups_under_30": under_30[:max_groups_under_30],
        "groups_under_30_omitted": under_30_omitted,
    }


def target_by_attribute(
    df: pd.DataFrame,
    attr: str,
    target: str,
    pos_label: Any,
    *,
    include_col_percent: bool = False,
) -> dict[str, Any]:
    """
    Compact crosstab: counts + row % + positive rates.
    ``col_percent_within_label`` is omitted by default (often doubles payload size).
    """
    crosstab = pd.crosstab(
        df[attr].fillna("<NA>").astype(str),
        df[target].fillna("<NA>").astype(str),
        dropna=False,
    )
    counts = {
        str(r): {str(c): int(crosstab.loc[r, c]) for c in crosstab.columns}
        for r in crosstab.index
    }
    row_pct: dict[str, dict[str, Optional[float]]] = {}
    for r, cols in counts.items():
        row_total = sum(cols.values())
        row_pct[r] = {c: _pct(n, row_total) for c, n in cols.items()}
    pos_rates: dict[str, Optional[float]] = {}
    pos_key = None
    for c in crosstab.columns:
        if c == pos_label or str(c) == str(pos_label):
            pos_key = c
            break
    if pos_key is not None:
        for r in crosstab.index:
            row_total = int(crosstab.loc[r].sum())
            pos = int(crosstab.loc[r, pos_key])
            pos_rates[str(r)] = _pct(pos, row_total)
    out: dict[str, Any] = {
        "counts": counts,
        "row_percent_within_group": row_pct,
        "positive_rate_by_group": pos_rates,
    }
    if include_col_percent:
        col_pct: dict[str, dict[str, Optional[float]]] = {}
        for c in crosstab.columns:
            col_total = int(crosstab[c].sum())
            col_pct[str(c)] = {
                str(r): _pct(int(crosstab.loc[r, c]), col_total) for r in crosstab.index
            }
        out["col_percent_within_label"] = col_pct
    return out


def intersection_representation(
    df: pd.DataFrame,
    attrs: list[str],
    target: str,
    pos_label: Any,
    *,
    max_groups: int = _FAIRNESS_MAX_INTERSECTION_GROUPS,
) -> dict[str, Any]:
    if len(attrs) < 2:
        return {}
    tmp = df.copy()
    tmp["_intersection"] = tmp[attrs].fillna("<NA>").astype(str).agg(" | ".join, axis=1)
    collapsed, trunc = _topk_collapse_series(tmp["_intersection"], max_groups)
    tmp["_intersection"] = collapsed
    n_orig = int(trunc.get("n_groups_original") or 0)
    if n_orig > max_groups * 3:
        # Extremely combinatorial — skip heavy crosstab; keep compact representation only
        return {
            "attributes": attrs,
            "skipped_crosstab": True,
            "reason": (
                f"Intersection has {n_orig} groups; crosstab skipped to keep the report "
                f"agent-friendly (max={max_groups})."
            ),
            "representation": representation(tmp, "_intersection"),
            "truncation": trunc,
            "target_by_intersection": {},
        }
    return {
        "attributes": attrs,
        "representation": representation(tmp, "_intersection"),
        "truncation": trunc,
        "target_by_intersection": target_by_attribute(
            tmp, "_intersection", target, pos_label, include_col_percent=False
        ),
    }


def _positive_rate(y: pd.Series, pos_label: Any) -> float:
    y = pd.Series(y)
    n = len(y)
    if n == 0:
        return float("nan")
    return float((y == pos_label).sum()) / float(n)


def _di_spd(y: pd.Series, prot: pd.Series, priv_group: str, pos_label: Any) -> Tuple[float, float]:
    priv_mask = prot.astype(str) == str(priv_group)
    p_priv = _positive_rate(y[priv_mask], pos_label)
    p_unpriv = _positive_rate(y[~priv_mask], pos_label)
    di = p_unpriv / p_priv if p_priv > 0 else float("nan")
    spd = p_unpriv - p_priv
    return di, spd


def _smoothed_edf_fallback(
    y: pd.Series,
    prot: Union[pd.Series, pd.DataFrame],
    pos_label: Any,
    concentration: float = 1.0,
) -> float:
    if isinstance(prot, pd.DataFrame):
        groups = prot.astype(str).agg(" | ".join, axis=1)
    else:
        groups = prot.astype(str)
    alpha = float(concentration)
    rates = []
    for _, idx in groups.groupby(groups).groups.items():
        n_s = len(idx)
        n_pos = int((y.loc[idx] == pos_label).sum())
        rate = (n_pos + alpha) / (n_s + 2.0 * alpha)
        rates.append(rate)
    if len(rates) < 2:
        return 0.0
    logs = [math.log(max(r, 1e-12)) for r in rates]
    lognegs = [math.log(max(1.0 - r, 1e-12)) for r in rates]
    pos_gap = max(abs(a - b) for i, a in enumerate(logs) for b in logs[i + 1 :])
    neg_gap = max(abs(a - b) for i, a in enumerate(lognegs) for b in lognegs[i + 1 :])
    return float(max(pos_gap, neg_gap))


def compute_aif360_metrics(
    df: pd.DataFrame,
    target: str,
    protected_attrs: list[str],
    privileged: dict[str, str],
    pos_label: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "library": "aif360",
        "api": "aif360.sklearn.metrics",
        "backend": "aif360",
        "note": (
            "Dataset-level metrics: y_true = labels, no y_pred. "
            "DI/SPD use privileged vs rest; smoothed_edf is multi-group."
        ),
        "per_attribute": {},
        "intersectional": {},
        "import_errors": [],
    }

    aif_di = aif_spd = aif_sedf = aif_base = None
    try:
        from aif360.sklearn.metrics import (
            disparate_impact_ratio as aif_di,
            statistical_parity_difference as aif_spd,
            smoothed_edf as aif_sedf,
            base_rate as aif_base,
        )
    except ImportError as e:
        out["import_errors"].append(str(e))
        out["backend"] = "fallback_numpy"
        out["hint"] = "pip install aif360"

    y = df[target]
    if not isinstance(y, pd.Series):
        y = pd.Series(y, name=target)
    else:
        y = y.copy()
        y.name = target

    for attr in protected_attrs:
        priv = privileged.get(attr)
        prot = df[attr].astype(str)
        y_idx = y.copy()
        y_idx.index = pd.MultiIndex.from_arrays([prot], names=[attr])
        entry: dict[str, Any] = {"privileged_group": priv, "functions": {}}

        try:
            br = (
                aif_base(y_idx, pos_label=pos_label)
                if aif_base is not None
                else _positive_rate(y, pos_label)
            )
            entry["functions"]["base_rate_overall"] = {
                "value": _safe_float(br),
                "meaning": "P(Y=pos_label) overall",
            }
        except Exception as e:
            entry["functions"]["base_rate_overall"] = {"error": str(e)}

        if priv is not None:
            try:
                if aif_di is not None:
                    di = aif_di(y_idx, prot_attr=attr, priv_group=priv, pos_label=pos_label)
                    spd = aif_spd(y_idx, prot_attr=attr, priv_group=priv, pos_label=pos_label)
                else:
                    di, spd = _di_spd(y, prot, priv, pos_label)
                entry["functions"]["disparate_impact_ratio"] = {
                    "value": _safe_float(di),
                    "ideal": 1.0,
                    "rule_of_thumb": "Often flagged if < 0.8 or > 1.25",
                    "meaning": "P(Y=pos|unprivileged) / P(Y=pos|privileged)",
                    "aif360": "aif360.sklearn.metrics.disparate_impact_ratio",
                }
                entry["functions"]["statistical_parity_difference"] = {
                    "value": _safe_float(spd),
                    "ideal": 0.0,
                    "meaning": "P(Y=pos|unprivileged) - P(Y=pos|privileged)",
                    "aif360": "aif360.sklearn.metrics.statistical_parity_difference",
                }
            except Exception as e:
                entry["functions"]["disparate_impact_ratio"] = {"error": str(e)}
                entry["functions"]["statistical_parity_difference"] = {"error": str(e)}

        try:
            if aif_sedf is not None:
                sedf = aif_sedf(y_idx, prot_attr=attr, pos_label=pos_label, concentration=1.0)
            else:
                sedf = _smoothed_edf_fallback(y, prot, pos_label, concentration=1.0)
            entry["functions"]["smoothed_edf"] = {
                "value": _safe_float(sedf),
                "ideal": 0.0,
                "meaning": "Max smoothed log-ratio gap across groups; lower is fairer",
                "aif360": "aif360.sklearn.metrics.smoothed_edf",
            }
        except Exception as e:
            entry["functions"]["smoothed_edf"] = {"error": str(e)}

        if priv is not None:
            pairwise = []
            # Prefer larger unprivileged groups; cap list for agent-friendly payloads
            group_sizes = prot.astype(str).value_counts()
            candidates = [
                g
                for g in group_sizes.index.tolist()
                if str(g) != str(priv) and str(g) != _FAIRNESS_OTHER_LABEL
            ]
            omitted_pw = max(0, len(candidates) - _FAIRNESS_MAX_PAIRWISE)
            for g in candidates[:_FAIRNESS_MAX_PAIRWISE]:
                mask = prot.astype(str).isin([str(priv), str(g)])
                y_sub = y[mask].copy()
                p_sub = prot[mask].astype(str)
                try:
                    if aif_di is not None:
                        y_sub_idx = y_sub.copy()
                        y_sub_idx.index = pd.MultiIndex.from_arrays([p_sub], names=[attr])
                        di_v = aif_di(
                            y_sub_idx, prot_attr=attr, priv_group=priv, pos_label=pos_label
                        )
                        spd_v = aif_spd(
                            y_sub_idx, prot_attr=attr, priv_group=priv, pos_label=pos_label
                        )
                    else:
                        di_v, spd_v = _di_spd(y_sub, p_sub, priv, pos_label)
                    pairwise.append(
                        {
                            "privileged": priv,
                            "unprivileged": str(g),
                            "disparate_impact_ratio": _safe_float(di_v),
                            "statistical_parity_difference": _safe_float(spd_v),
                            "n": int(mask.sum()),
                        }
                    )
                except Exception as e:
                    pairwise.append(
                        {"privileged": priv, "unprivileged": str(g), "error": str(e)}
                    )
            entry["pairwise_vs_privileged"] = pairwise
            if omitted_pw:
                entry["pairwise_omitted"] = omitted_pw

        out["per_attribute"][attr] = entry

    if len(protected_attrs) >= 2:
        try:
            inter = df[protected_attrs].astype(str).agg(" | ".join, axis=1)
            if aif_sedf is not None:
                y_i = y.copy()
                y_i.index = pd.MultiIndex.from_arrays(
                    [df[protected_attrs[0]].astype(str), df[protected_attrs[1]].astype(str)],
                    names=protected_attrs,
                )
                sedf_i = aif_sedf(
                    y_i, prot_attr=protected_attrs, pos_label=pos_label, concentration=1.0
                )
            else:
                sedf_i = _smoothed_edf_fallback(
                    y, df[protected_attrs], pos_label, concentration=1.0
                )
            out["intersectional"] = {
                "attributes": protected_attrs,
                "smoothed_edf": {
                    "value": _safe_float(sedf_i),
                    "ideal": 0.0,
                    "aif360": "aif360.sklearn.metrics.smoothed_edf(prot_attr=[...])",
                    "meaning": "Intersectional smoothed EDF across protected-attribute cells",
                },
                "n_observed_cells": int(inter.nunique()),
            }
        except Exception as e:
            out["intersectional"] = {"error": str(e)}

    return out


def build_alerts(rep_by_attr: dict[str, Any], aif: dict[str, Any]) -> list[str]:
    alerts: list[str] = []
    for attr, rep in rep_by_attr.items():
        ratio = rep.get("max_min_ratio") or 0
        if ratio >= 3.0:
            alerts.append(
                f"{attr}: largest/smallest group ratio {ratio} (>= 3.0) - representation skew"
            )
        for g in rep.get("groups_under_30") or []:
            alerts.append(f"{attr}: group '{g}' has < 30 samples - treat metrics cautiously")
    for attr, entry in (aif.get("per_attribute") or {}).items():
        di = (entry.get("functions") or {}).get("disparate_impact_ratio", {}).get("value")
        if di is not None and (di < 0.8 or di > 1.25):
            alerts.append(
                f"{attr}: disparate_impact_ratio={di:.4f} outside [0.8, 1.25] "
                f"(privileged={entry.get('privileged_group')})"
            )
        spd = (entry.get("functions") or {}).get("statistical_parity_difference", {}).get("value")
        if spd is not None and abs(spd) >= 0.1:
            alerts.append(
                f"{attr}: statistical_parity_difference={spd:.4f} (|SPD| >= 0.1)"
            )
    return alerts


def resolve_protected_attributes(
    df: pd.DataFrame,
    *,
    target_column: Optional[str] = None,
    protected_attributes: Any = None,
    privileged_groups: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Decide which protected attributes to use.

    Returns None when fairness_profile should be skipped.
    """
    user_attrs, user_priv = normalize_protected_attributes_input(protected_attributes)
    if privileged_groups:
        for k, v in privileged_groups.items():
            if v is not None and str(v).strip() != "":
                user_priv[str(k)] = str(v)

    candidates = detect_protected_attribute_candidates(
        list(df.columns), exclude=[target_column] if target_column else None
    )
    candidate_names = [c["column"] for c in candidates]

    if user_attrs:
        source = "user"
        attrs = [a for a in user_attrs if a in df.columns]
        missing = [a for a in user_attrs if a not in df.columns]
        if missing:
            logger.warning("Ignoring protected_attributes not in dataframe: %s", missing)
        if not attrs:
            return None
    elif candidate_names:
        source = "heuristic"
        attrs = candidate_names
    else:
        return None

    # Category map for privilege hints
    cat_by_col = {c["column"]: c["category"] for c in candidates}
    privileged: Dict[str, str] = {}
    for a in attrs:
        if a in user_priv:
            privileged[a] = user_priv[a]
        else:
            inferred = infer_privileged_group(df[a], category=cat_by_col.get(a))
            if inferred is not None:
                privileged[a] = inferred

    return {
        "source": source,
        "protected_attributes": attrs,
        "privileged_groups": privileged,
        "heuristic_candidates": candidates,
    }


def build_fairness_profile(
    df: pd.DataFrame,
    *,
    target_column: Optional[str] = None,
    protected_attributes: Any = None,
    privileged_groups: Optional[Dict[str, str]] = None,
    pos_label: Any = None,
) -> Optional[Dict[str, Any]]:
    """
    Build the ``fairness_profile`` section for a bias report, or None to skip.
    """
    if df is None or df.empty:
        return None

    resolved = resolve_protected_attributes(
        df,
        target_column=target_column,
        protected_attributes=protected_attributes,
        privileged_groups=privileged_groups,
    )
    if not resolved:
        logger.info("No protected attributes (user or heuristic); skipping fairness_profile")
        return None

    attrs: List[str] = resolved["protected_attributes"]
    privileged: Dict[str, str] = resolved["privileged_groups"]
    source: str = resolved["source"]

    target = target_column if target_column and target_column in df.columns else None
    if not target:
        # Fairness metrics need a label; still emit representation-only profile
        logger.info(
            "Fairness profile without target_column: representation only for %s", attrs
        )
        rep = {a: representation(df, a) for a in attrs}
        return OrderedDict(
            [
                (
                    "config",
                    {
                        "target_column": None,
                        "pos_label": None,
                        "protected_attributes": attrs,
                        "privileged_groups": privileged,
                        "source": source,
                        "heuristic_candidates": resolved.get("heuristic_candidates") or [],
                    },
                ),
                ("global_target_balance", None),
                ("representation", rep),
                ("target_by_attribute", {}),
                ("intersection", {}),
                ("aif360_metrics", {"skipped": True, "reason": "no target_column"}),
                ("alerts", build_alerts(rep, {"per_attribute": {}})),
            ]
        )

    y = df[target]

    # Continuous / high-cardinality targets: representation only (no AIF360 crosstabs).
    # Treating every distinct float score as a class produces multi-MB reports and
    # invalid DI/SPD (e.g. accessibility_score with hundreds of unique values).
    if not is_discrete_fairness_target(y):
        n_unique = int(y.nunique(dropna=True))
        logger.info(
            "Fairness profile: target '%s' is continuous/high-cardinality "
            "(n_unique=%s); skipping AIF360 crosstabs (representation only)",
            target,
            n_unique,
        )
        skip_reason = (
            f"Target '{target}' looks continuous or has too many distinct values "
            f"(n_unique={n_unique}, max_discrete={_FAIRNESS_MAX_DISCRETE_CLASSES}). "
            "Classification-style fairness (DI/SPD, label crosstabs) was skipped. "
            "Regression group fairness is not implemented yet."
        )
        df_rep = df.copy()
        trunc_cont: dict[str, Any] = {}
        for a in attrs:
            collapsed, meta = _topk_collapse_series(df_rep[a], _FAIRNESS_MAX_GROUPS_PER_ATTR)
            df_rep[a] = collapsed
            trunc_cont[a] = meta
        rep = {a: representation(df_rep, a) for a in attrs}
        heur = resolved.get("heuristic_candidates") or []
        if isinstance(heur, list) and len(heur) > 10:
            heur = heur[:10]
        return OrderedDict(
            [
                (
                    "config",
                    {
                        "target_column": target,
                        "pos_label": None,
                        "protected_attributes": attrs,
                        "privileged_groups": privileged,
                        "source": source,
                        "heuristic_candidates": heur,
                        "target_kind": "continuous",
                        "fairness_mode": "representation_only",
                        "truncation": trunc_cont,
                    },
                ),
                (
                    "global_target_balance",
                    {
                        "summary": _continuous_target_summary(y),
                        "counts": None,
                        "comment": skip_reason,
                    },
                ),
                ("representation", rep),
                ("target_by_attribute", {}),
                ("intersection", {}),
                (
                    "aif360_metrics",
                    {
                        "skipped": True,
                        "reason": skip_reason,
                        "library": "aif360",
                    },
                ),
                ("alerts", build_alerts(rep, {"per_attribute": {}})),
            ]
        )

    pos = _infer_pos_label(y, pos_label)
    try:
        pos_out: Any = pos.item() if hasattr(pos, "item") else pos
    except Exception:
        pos_out = pos

    # Collapse high-cardinality protected attrs (and rare labels) so crosstabs stay small
    df_f = df.copy()
    truncation: dict[str, Any] = {}
    for a in attrs:
        collapsed, meta = _topk_collapse_series(
            df_f[a], _FAIRNESS_MAX_GROUPS_PER_ATTR
        )
        df_f[a] = collapsed
        truncation[a] = meta
    y_f = df_f[target]
    y_collapsed, y_trunc = _topk_collapse_series(
        y_f, _FAIRNESS_MAX_DISCRETE_CLASSES
    )
    if y_trunc.get("truncated"):
        df_f[target] = y_collapsed
        y_f = y_collapsed
        truncation[target] = y_trunc
        # Re-infer pos_label if the original positive class was collapsed away
        if pos_out is not None and str(pos_out) not in set(y_f.unique().astype(str)):
            pos = _infer_pos_label(y_f, None)
            try:
                pos_out = pos.item() if hasattr(pos, "item") else pos
            except Exception:
                pos_out = pos

    total = int(len(df_f))
    target_vc = y_f.value_counts(dropna=False)
    target_balance = {
        str(k): {"count": int(v), "percent": _pct(int(v), total)}
        for k, v in target_vc.items()
    }
    rep = {a: representation(df_f, a) for a in attrs}
    tba = {
        a: target_by_attribute(
            df_f, a, target, pos, include_col_percent=False
        )
        for a in attrs
    }
    inter = intersection_representation(df_f, attrs, target, pos)
    aif = compute_aif360_metrics(df_f, target, attrs, privileged, pos)
    alerts = build_alerts(rep, aif)

    # Keep heuristic candidate list short in the payload
    heur = resolved.get("heuristic_candidates") or []
    if isinstance(heur, list) and len(heur) > 10:
        heur = heur[:10]

    return OrderedDict(
        [
            (
                "config",
                {
                    "target_column": target,
                    "pos_label": pos_out,
                    "protected_attributes": attrs,
                    "privileged_groups": privileged,
                    "source": source,
                    "heuristic_candidates": heur,
                    "target_kind": "discrete",
                    "fairness_mode": "classification",
                    "truncation": truncation,
                    "payload_limits": {
                        "max_groups_per_attribute": _FAIRNESS_MAX_GROUPS_PER_ATTR,
                        "max_discrete_classes": _FAIRNESS_MAX_DISCRETE_CLASSES,
                        "max_intersection_groups": _FAIRNESS_MAX_INTERSECTION_GROUPS,
                        "max_pairwise": _FAIRNESS_MAX_PAIRWISE,
                        "col_percent_within_label": False,
                    },
                },
            ),
            (
                "global_target_balance",
                {
                    "counts": target_balance,
                    "comment": (
                        "Overall label balance; use representation / target_by_attribute "
                        "for subgroup skew that global counts hide. High-cardinality "
                        "groups may be collapsed into '__other__'."
                    ),
                },
            ),
            ("representation", rep),
            ("target_by_attribute", tba),
            ("intersection", inter),
            ("aif360_metrics", aif),
            ("alerts", alerts),
        ]
    )


def strip_duplicate_categorical_stats(report: dict, protected_attrs: Sequence[str]) -> dict:
    """
    Remove protected-attribute columns from coarse EDA categorical summaries
    when a fairness_profile already covers them (avoids duplicate UI noise).
    """
    if not report or not protected_attrs:
        return report
    drop = {str(a) for a in protected_attrs}
    for key in ("categorical_value_counts", "unique_values"):
        block = report.get(key)
        if isinstance(block, dict):
            report[key] = {k: v for k, v in block.items() if str(k) not in drop}
    return report
