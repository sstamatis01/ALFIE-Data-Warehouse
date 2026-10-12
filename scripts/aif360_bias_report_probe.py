#!/usr/bin/env python3
"""
Probe script: offline example of fairness_profile JSON (AIF360 / fallback).

Production path lives in ``app.services.fairness_profile`` and is invoked from
``kafka_bias_detector_consumer_example.py`` when building the bias report.
Protected attributes: Kafka ``input.protected_attributes`` (user) else header heuristics.

Uses the driver-drowsiness tabular CSV (label + gender + ethnicity) to show:
  1) Representation / contingency tables
  2) Dataset-level AIF360 group fairness metrics (sklearn API preferred)
  3) A JSON blob shaped like AutoDW ``report.fairness_profile``

This does NOT mitigate data. Metrics-only exploration / regression aid.

Usage (from repo root):
  pip install 'aif360' pandas scikit-learn numpy
  python scripts/aif360_bias_report_probe.py \\
    --csv "path/to/tabular_data_modified (1).csv" \\
    --out scripts/aif360_probe_output/example_bias_report_fairness.json

Docker (no local Python):
  docker run --rm -v "%CD%":/work -v "C:/Users/Stamatis/ALFIE-Data-Warehouse-main/updated_bias_detection":/data \\
    -w /work python:3.11-slim bash -c "pip install -q aif360 pandas scikit-learn numpy && \\
    python scripts/aif360_bias_report_probe.py --csv '/data/tabular_data_modified (1).csv'"
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_PROTECTED = ["gender", "ethnicity"]
DEFAULT_TARGET = "label"
# Positive / favorable class for binary label metrics (1 = alert in this CSV).
DEFAULT_POS_LABEL = 1
# Privileged groups used for binary DI / SPD (configurable in a real AutoDW job).
DEFAULT_PRIVILEGED = {
    "gender": "Male",
    "ethnicity": "Caucasian",
}


def _pct(n: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(float(n) / float(total), 6)


def _safe_float(x: Any) -> float | None:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def representation(df: pd.DataFrame, col: str) -> dict[str, Any]:
    vc = df[col].fillna("<NA>").astype(str).value_counts(dropna=False)
    total = int(len(df))
    groups = {
        str(k): {"count": int(v), "percent": _pct(int(v), total)}
        for k, v in vc.items()
    }
    counts = [g["count"] for g in groups.values()]
    return {
        "groups": groups,
        "n_groups": len(groups),
        "largest_group": max(groups, key=lambda k: groups[k]["count"]) if groups else None,
        "smallest_group": min(groups, key=lambda k: groups[k]["count"]) if groups else None,
        "max_min_ratio": round(max(counts) / max(min(counts), 1), 3) if counts else None,
        "groups_under_30": [k for k, g in groups.items() if g["count"] < 30],
    }


def target_by_attribute(df: pd.DataFrame, attr: str, target: str) -> dict[str, Any]:
    crosstab = pd.crosstab(
        df[attr].fillna("<NA>").astype(str),
        df[target].fillna("<NA>").astype(str),
        dropna=False,
    )
    counts = {r: {c: int(crosstab.loc[r, c]) for c in crosstab.columns} for r in crosstab.index}
    row_pct: dict[str, dict[str, float | None]] = {}
    for r, cols in counts.items():
        row_total = sum(cols.values())
        row_pct[r] = {c: _pct(n, row_total) for c, n in cols.items()}
    col_pct: dict[str, dict[str, float | None]] = {}
    for c in crosstab.columns:
        col_total = int(crosstab[c].sum())
        col_pct[str(c)] = {
            str(r): _pct(int(crosstab.loc[r, c]), col_total) for r in crosstab.index
        }
    # Positive-rate per group when target is binary-ish
    pos_rates = {}
    if str(DEFAULT_POS_LABEL) in [str(c) for c in crosstab.columns] or DEFAULT_POS_LABEL in crosstab.columns:
        pos_key = DEFAULT_POS_LABEL if DEFAULT_POS_LABEL in crosstab.columns else str(DEFAULT_POS_LABEL)
        for r in crosstab.index:
            row_total = int(crosstab.loc[r].sum())
            pos = int(crosstab.loc[r, pos_key]) if pos_key in crosstab.columns else 0
            pos_rates[str(r)] = _pct(pos, row_total)
    return {
        "counts": counts,
        "row_percent_within_group": row_pct,
        "col_percent_within_label": col_pct,
        "positive_rate_by_group": pos_rates,
    }


def intersection_representation(df: pd.DataFrame, attrs: list[str], target: str) -> dict[str, Any]:
    if len(attrs) < 2:
        return {}
    keys = df[attrs].fillna("<NA>").astype(str).agg(" | ".join, axis=1)
    tmp = df.copy()
    tmp["_intersection"] = keys
    rep = representation(tmp, "_intersection")
    by_label = target_by_attribute(tmp, "_intersection", target)
    return {
        "attributes": attrs,
        "representation": rep,
        "target_by_intersection": by_label,
        "empty_combos_note": (
            "Missing gender×ethnicity combinations are informative: "
            "this CSV nests ethnicity heavily by gender (e.g. Middle Eastern only Female, "
            "African/Unknown only Male)."
        ),
    }


def _positive_rate(y: pd.Series, pos_label: int) -> float:
    y = pd.Series(y)
    n = len(y)
    if n == 0:
        return float("nan")
    return float((y == pos_label).sum()) / float(n)


def _di_spd(y: pd.Series, prot: pd.Series, priv_group: str, pos_label: int) -> tuple[float, float]:
    """Fallback DI / SPD: unprivileged = everyone not in privileged group."""
    priv_mask = prot.astype(str) == str(priv_group)
    p_priv = _positive_rate(y[priv_mask], pos_label)
    p_unpriv = _positive_rate(y[~priv_mask], pos_label)
    di = p_unpriv / p_priv if p_priv > 0 else float("nan")
    spd = p_unpriv - p_priv
    return di, spd


def _smoothed_edf_fallback(
    y: pd.Series, prot: pd.Series | pd.DataFrame, pos_label: int, concentration: float = 1.0
) -> float:
    """
    Smoothed empirical differential fairness (Foulds et al.), dataset-level.
    Matches the spirit of aif360.sklearn.metrics.smoothed_edf when only y_true is used.
    """
    if isinstance(prot, pd.DataFrame):
        groups = prot.astype(str).agg(" | ".join, axis=1)
    else:
        groups = prot.astype(str)
    alpha = float(concentration)
    rates = []
    for _, idx in groups.groupby(groups).groups.items():
        n_s = len(idx)
        n_pos = int((y.loc[idx] == pos_label).sum())
        # Dirichlet-smoothed positive rate; |R_Y|=2 for binary labels
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
    pos_label: int,
) -> dict[str, Any]:
    """
    Call AIF360 sklearn metrics on the label distribution (dataset-level, no model).

    Functions exercised (when aif360 is installed):
      - aif360.sklearn.metrics.disparate_impact_ratio
      - aif360.sklearn.metrics.statistical_parity_difference
      - aif360.sklearn.metrics.smoothed_edf
      - aif360.sklearn.metrics.base_rate

    If aif360 is missing, the same quantities are computed with a local fallback
    so this probe still produces a concrete example report.
    """
    out: dict[str, Any] = {
        "library": "aif360",
        "api": "aif360.sklearn.metrics",
        "backend": "aif360",
        "note": (
            "Dataset-level metrics: y_true = labels, no y_pred. "
            "DI/SPD need a binary privileged vs rest (or privileged vs unprivileged) view; "
            "smoothed_edf supports multi-group / intersectional protected attributes."
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
        out["hint"] = "pip install aif360  # fallback formulas used for this run"

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

        entry: dict[str, Any] = {
            "privileged_group": priv,
            "functions": {},
        }

        try:
            if aif_base is not None:
                br = aif_base(y_idx, pos_label=pos_label)
            else:
                br = _positive_rate(y, pos_label)
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
                    "rule_of_thumb": "Often flagged if < 0.8 or > 1.25 (four-fifths rule)",
                    "meaning": "P(Y=1|unprivileged) / P(Y=1|privileged)",
                    "aif360": "aif360.sklearn.metrics.disparate_impact_ratio",
                }
                entry["functions"]["statistical_parity_difference"] = {
                    "value": _safe_float(spd),
                    "ideal": 0.0,
                    "meaning": "P(Y=1|unprivileged) - P(Y=1|privileged)",
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
                "meaning": (
                    "Max log-ratio gap in (smoothed) positive rates across groups; "
                    "lower is fairer. Captures multi-category imbalance (e.g. ethnicity)."
                ),
                "aif360": "aif360.sklearn.metrics.smoothed_edf",
            }
        except Exception as e:
            entry["functions"]["smoothed_edf"] = {"error": str(e)}

        if priv is not None:
            pairwise = []
            for g in sorted(prot.unique()):
                if str(g) == str(priv):
                    continue
                mask = prot.isin([priv, g])
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
                    "meaning": "Intersectional smoothed EDF across gender×ethnicity cells",
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


def build_report(
    df: pd.DataFrame,
    *,
    target: str,
    protected_attrs: list[str],
    privileged: dict[str, str],
    pos_label: int,
    source_csv: str,
) -> dict[str, Any]:
    # Global target balance (what you already see today)
    target_vc = df[target].value_counts(dropna=False)
    total = int(len(df))
    target_balance = {
        str(k): {"count": int(v), "percent": _pct(int(v), total)}
        for k, v in target_vc.items()
    }

    rep = {a: representation(df, a) for a in protected_attrs}
    tba = {a: target_by_attribute(df, a, target) for a in protected_attrs}
    inter = intersection_representation(df, protected_attrs, target)
    aif = compute_aif360_metrics(df, target, protected_attrs, privileged, pos_label)
    alerts = build_alerts(rep, aif)

    # Map label → frame_class if present (helps humans reading the report)
    label_legend = None
    if "frame_class" in df.columns:
        legend = (
            df.groupby(target)["frame_class"]
            .agg(lambda s: s.value_counts().to_dict())
            .to_dict()
        )
        label_legend = {str(k): v for k, v in legend.items()}

    return OrderedDict(
        [
            (
                "fairness_profile",
                OrderedDict(
                    [
                        (
                            "config",
                            {
                                "source_csv": source_csv,
                                "target_column": target,
                                "pos_label": pos_label,
                                "protected_attributes": protected_attrs,
                                "privileged_groups": privileged,
                                "label_legend_from_frame_class": label_legend,
                            },
                        ),
                        (
                            "global_target_balance",
                            {
                                "counts": target_balance,
                                "comment": (
                                    "Looks roughly balanced overall — subgroup views below "
                                    "are needed to see gender/ethnicity skew."
                                ),
                            },
                        ),
                        ("representation", rep),
                        ("target_by_attribute", tba),
                        ("intersection", inter),
                        ("aif360_metrics", aif),
                        ("alerts", alerts),
                        (
                            "integration_notes_for_autodw",
                            [
                                "Bias trigger / dataset metadata must pass protected_attributes + optional privileged_groups + pos_label.",
                                "Store this object under bias_report['fairness_profile'] (report is already Any JSON).",
                                "Prefer aif360.sklearn.metrics for new code; tables above do not need AIF360 but metrics do.",
                                "For multi-class ethnicity, always keep pairwise + smoothed_edf — binary DI alone collapses groups.",
                                "Sparse cells (Asian=7) should surface as alerts; do not auto-mitigate on tiny n without review.",
                                "Mitigation (DI Remover, Reweighing, …) is a separate later phase; this probe is metrics-only.",
                            ],
                        ),
                    ]
                ),
            )
        ]
    )


def print_human_summary(report: dict[str, Any]) -> None:
    fp = report["fairness_profile"]
    print("=" * 72)
    print("GLOBAL TARGET BALANCE")
    print(json.dumps(fp["global_target_balance"]["counts"], indent=2))
    print()
    print("REPRESENTATION")
    for attr, rep in fp["representation"].items():
        print(f"  [{attr}] max/min ratio={rep.get('max_min_ratio')}  under30={rep.get('groups_under_30')}")
        for g, st in rep["groups"].items():
            print(f"    {g:20s}  n={st['count']:4d}  ({100*(st['percent'] or 0):5.1f}%)")
    print()
    print("POSITIVE RATE BY GROUP (label == pos_label)")
    for attr, tba in fp["target_by_attribute"].items():
        print(f"  [{attr}]")
        for g, rate in (tba.get("positive_rate_by_group") or {}).items():
            print(f"    {g:20s}  P(Y=1)={rate}")
    print()
    print("AIF360 METRICS")
    aif = fp["aif360_metrics"]
    if aif.get("import_errors"):
        print("  IMPORT FAILED:", aif["import_errors"])
        print("  ", aif.get("hint"))
    else:
        for attr, entry in (aif.get("per_attribute") or {}).items():
            print(f"  [{attr}] privileged={entry.get('privileged_group')}")
            for name, payload in (entry.get("functions") or {}).items():
                if "value" in payload:
                    print(f"    {name}: {payload['value']}")
                elif "error" in payload:
                    print(f"    {name}: ERROR {payload['error']}")
            for row in entry.get("pairwise_vs_privileged") or []:
                if "error" in row:
                    print(f"    vs {row.get('unprivileged')}: ERROR {row['error']}")
                else:
                    print(
                        f"    vs {row['unprivileged']}: DI={row['disparate_impact_ratio']} "
                        f"SPD={row['statistical_parity_difference']} (n={row['n']})"
                    )
        inter = aif.get("intersectional") or {}
        if "smoothed_edf" in inter:
            print(f"  [intersection] smoothed_edf={inter['smoothed_edf'].get('value')}")
        elif "error" in inter:
            print(f"  [intersection] ERROR {inter['error']}")
    print()
    print("ALERTS")
    for a in fp["alerts"]:
        print(f"  - {a}")
    print("=" * 72)


def main() -> int:
    p = argparse.ArgumentParser(description="AIF360 bias-report probe for protected attributes")
    p.add_argument(
        "--csv",
        default=r"c:\Users\Stamatis\ALFIE-Data-Warehouse-main\updated_bias_detection\tabular_data_modified (1).csv",
        help="Path to tabular CSV",
    )
    p.add_argument("--target", default=DEFAULT_TARGET)
    p.add_argument("--protected", nargs="+", default=DEFAULT_PROTECTED)
    p.add_argument("--pos-label", type=int, default=DEFAULT_POS_LABEL)
    p.add_argument(
        "--out",
        default="scripts/aif360_probe_output/example_bias_report_fairness.json",
        help="Where to write the example JSON report section",
    )
    args = p.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        return 1

    df = pd.read_csv(csv_path)
    missing = [c for c in [args.target, *args.protected] if c not in df.columns]
    if missing:
        print(f"Missing columns: {missing}. Available: {list(df.columns)}", file=sys.stderr)
        return 1

    privileged = {k: v for k, v in DEFAULT_PRIVILEGED.items() if k in args.protected}
    report = build_report(
        df,
        target=args.target,
        protected_attrs=list(args.protected),
        privileged=privileged,
        pos_label=args.pos_label,
        source_csv=str(csv_path),
    )

    print_human_summary(report)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nWrote example report JSON → {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
