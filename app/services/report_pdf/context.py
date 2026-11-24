"""Turns the raw AutoDW JSON into a render context. ALL data mapping rules live here.

Rules (see CURSOR_IMPLEMENTATION_GUIDE.md §5):
* Never invent numbers. Derived numbers (percent of rows, rate = DI x privileged rate) are
  computed from JSON values only, and anything missing becomes None -> "Not available".
* Thresholds are read from the JSON (class_imbalance.thresholds, alert strings, rule_of_thumb)
  and fall back to ReportConfig only when absent.
* Severity of alerts is a configurable mapping (ReportConfig.severity_by_kind).
* Transformation steps: original value = `original_value` OR `original_missing_values`;
  dict values (SMOTE class counts) are rendered as "0: 614 · 1: 700" / bar chart.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
from markupsafe import Markup, escape

from . import charts
from .config import PALETTE as C, ReportConfig

pct = charts.pct


# ----------------------------------------------------------------------------- helpers
def g(d: Any, path: str, default=None):
    """Safe nested getter: g(doc, 'report.fairness_profile.alerts')."""
    cur = d
    for p in path.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


def num(x) -> Optional[float]:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def fmt_value(v: Any) -> str:
    """Human formatting for transformation values (fixes '[object Object]' and float noise)."""
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, dict):
        return " · ".join(f"{k}: {fmt_value(x)}" for k, x in v.items())
    if isinstance(v, list):
        return ", ".join(fmt_value(x) for x in v)
    if isinstance(v, float):
        if abs(v) >= 1e5:
            return f"{v:,.0f}"
        out = f"{v:.4f}".rstrip("0").rstrip(".")
        return "0" if out in ("-0", "") else out
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def fmt_time(v: Any, tz: str) -> str:
    if v is None:
        return "—"
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return v
    if isinstance(v, datetime):
        if v.tzinfo is None:          # AutoDW stores UTC; bias created_at is emitted without 'Z'
            v = v.replace(tzinfo=timezone.utc)
        z = timezone.utc if tz == "UTC" else ZoneInfo(tz)   # ZoneInfo needs tzdata (pip install tzdata in slim images)
        local = v.astimezone(z)
        off = local.utcoffset()
        label = "UTC" if tz == "UTC" else f"UTC{'+' if off.total_seconds() >= 0 else '-'}{abs(int(off.total_seconds() // 3600))}"
        return local.strftime("%d %b %Y, %H:%M") + f" ({label})"
    return str(v)


def B(x) -> Markup:
    return Markup("<b>%s</b>") % x


def _float_in(pattern: str, text: str) -> Optional[float]:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


# ----------------------------------------------------------------------------- normalise
def normalise_bias(doc: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (meta, report). Accepts the stored document or just the inner report."""
    if isinstance(doc, dict) and isinstance(doc.get("report"), dict) and (
            "shape" in doc["report"] or "fairness_profile" in doc["report"] or "columns" in doc["report"]):
        return doc, doc["report"]
    return {}, doc or {}


def normalise_transformation(doc: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if doc is None:
        return {}, []
    if isinstance(doc, list):
        return {}, doc
    steps = doc.get("report")
    if isinstance(steps, list):
        return doc, steps
    if isinstance(steps, dict) and isinstance(steps.get("steps"), list):   # forward-compatible
        return doc, steps["steps"]
    return doc, []


# ----------------------------------------------------------------------------- main
def build_context(bias_doc: Dict[str, Any], transformation_doc: Any = None,
                  cfg: Optional[ReportConfig] = None) -> Dict[str, Any]:
    cfg = cfg or ReportConfig()
    meta, R = normalise_bias(bias_doc)
    tmeta, steps = normalise_transformation(transformation_doc)
    FP = R.get("fairness_profile") or {}
    AIF = g(FP, "aif360_metrics.per_attribute", {}) or {}
    rep = FP.get("representation") or {}
    tba = FP.get("target_by_attribute") or {}
    ci = R.get("class_imbalance") or {}
    shape = R.get("shape") or [None, None]
    rows, ncol = (shape + [None, None])[:2]
    rows_n = rows or ci.get("n_rows")
    alerts_raw: List[str] = list(FP.get("alerts") or [])
    ci_alerts: List[str] = [a if isinstance(a, str) else str(a) for a in (ci.get("alerts") or [])]

    # ---- thresholds (JSON first, config fallback) ----
    all_alert_text = " ".join(alerts_raw)
    rep_thr = _float_in(r"ratio [\d.]+ \(>= ([\d.]+)\)", all_alert_text) or cfg.representation_ratio
    spd_thr = _float_in(r"\|SPD\| >= ([\d.]+)", all_alert_text) or cfg.spd_abs
    m = re.search(r"outside \[([\d.]+), ([\d.]+)\]", all_alert_text)
    di_band = (float(m.group(1)), float(m.group(2))) if m else None
    if di_band is None:
        rot = next((g(a, "functions.disparate_impact_ratio.rule_of_thumb") for a in AIF.values()
                    if g(a, "functions.disparate_impact_ratio.rule_of_thumb")), "")
        m = re.search(r"< ([\d.]+) or > ([\d.]+)", rot or "")
        di_band = (float(m.group(1)), float(m.group(2))) if m else cfg.di_band

    # ---- alerts -> structured ----
    def kind_of(a: str) -> str:
        if "disparate_impact" in a: return "disparate_impact"
        if "statistical_parity" in a: return "statistical_parity"
        if "representation" in a: return "representation"
        return "other"

    alerts = []
    for a in alerts_raw:
        attr, _, msg = a.partition(":")
        attr = attr.strip() if msg else ""
        k = kind_of(a)
        f_ = g(AIF, f"{attr}.functions", {}) or {}
        short = {"representation": f"representation skew ({g(rep, f'{attr}.max_min_ratio', '?')}×)",
                 "disparate_impact": f"disparate impact {g(f_, 'disparate_impact_ratio.value', float('nan')):.3f}",
                 "statistical_parity": f"parity difference {g(f_, 'statistical_parity_difference.value', float('nan')):+.3f}"}.get(k, (msg or a).strip()[:70])
        alerts.append(dict(attr=attr, kind=k, short=short, sev=cfg.severity_by_kind.get(k, "medium"),
                           raw=(msg or a).strip(), plain=_alert_plain(k, attr, rep, AIF, tba, di_band, spd_thr)))
    for a in ci_alerts:
        alerts.append(dict(attr=ci.get("target_column", ""), kind="class_imbalance", short=a[:70],
                           sev=cfg.severity_by_kind.get("class_imbalance", "medium"), raw=a,
                           plain=Markup("The target classes are imbalanced: %s") % a))
    n_high = sum(a["sev"] == "high" for a in alerts)
    n_med = sum(a["sev"] == "medium" for a in alerts)

    # ---- data-quality notices (derived observations, not AutoDW alerts) ----
    mv = R.get("missing_values") or {}
    miss_cells = sum(int(v.get("count", 0)) for v in mv.values()) if mv else None
    dup = R.get("duplicate_rows_count")
    od = R.get("outlier_detection") or {}
    ds = R.get("distribution_statistics") or {}
    target = R.get("target_column") or ci.get("target_column") or g(FP, "config.target_column")
    skew = {k: v.get("skew") for k, v in ds.items() if k != target and num(v.get("skew")) is not None}
    high_skew = [k for k, v in skew.items() if abs(v) > cfg.skew_notice_abs]
    cvc = R.get("categorical_value_counts") or {}
    inconsistent = {c: vc for c, vc in cvc.items()
                    if len({str(k).lower() for k in vc}) < len(vc)}
    inter = FP.get("intersection") or {}
    small_inter = g(inter, "representation.groups_under_30") or []
    notices = []
    if dup: notices.append(("Duplicate rows", f"{dup:,} rows" + (f" ({dup / rows_n * 100:.1f}%)" if rows_n else "")))
    for c, v in od.items():
        if (num(v.get("percent")) or 0) > cfg.outlier_notice_pct:
            notices.append(("Outliers", f"{c}: {v['percent']:.1f}%"))
    if high_skew: notices.append(("Skewed columns", ", ".join(high_skew)))
    for c in inconsistent: notices.append(("Inconsistent labels", c))
    if small_inter: notices.append(("Small subgroups", f"{len(small_inter)} groups < {cfg.small_group_n} rows"))

    # ---- status banner ----
    hi_attrs = sorted({a["attr"] for a in alerts if a["sev"] == "high" and a["attr"]})
    if n_high:
        status = dict(level="high", icon="✕", title=Markup("Needs attention: fairness issue with ") +
                      Markup(", ").join(Markup("<u>%s</u>") % x for x in hi_attrs))
    elif n_med:
        status = dict(level="medium", icon="▲", title=Markup("Review recommended: %d warning(s)") % n_med)
    else:
        status = dict(level="ok", icon="✓", title=Markup("No bias alerts raised"))
    ok_attrs = [a for a in (g(FP, "config.protected_attributes") or []) if a not in {x["attr"] for x in alerts}]
    sub = []
    if ci:
        sub.append("The target classes are balanced overall." if not ci_alerts and not ci.get("extreme_imbalance")
                   else "The target classes are imbalanced.")
    if hi_attrs:
        sub.append(f"The share of label = 1 differs strongly between groups of {', '.join(hi_attrs)}.")
    if ok_attrs:
        sub.append(f"{', '.join(a.capitalize() for a in ok_attrs)} looks fine.")
    status["subtitle"] = " ".join(sub)
    status["counts"] = [("high", n_high), ("medium", n_med), ("notice", len(notices))]

    tiles = [
        ("Rows × columns", f"{rows:,} × {ncol}" if rows and ncol else "—", ""),
        ("Missing cells", f"{miss_cells:,}" if miss_cells is not None else "—",
         f"{miss_cells / (rows * ncol) * 100:.2f}% of all cells" if miss_cells is not None and rows and ncol else ""),
        ("Duplicate rows", f"{dup:,}" if dup is not None else "—", f"{dup / rows_n * 100:.1f}% of rows" if dup is not None and rows_n else ""),
        ("Protected attributes", str(len(g(FP, "config.protected_attributes") or [])) if FP else "—",
         (", ".join(g(FP, "config.protected_attributes") or []) + (f" (detected: {g(FP, 'config.source')})" if g(FP, "config.source") else "")) if FP else "fairness profile not available"),
    ]
    mit = R.get("mitigation") or {}
    mit_tile = None
    if mit.get("mitigation_performed"):
        mit_tile = (f"{meta.get('dataset_version', '?')} → {mit.get('mitigated_dataset_version', '?')}",
                    f"{mit.get('transformation_count', '?')} steps logged")

    # ---- checks grid ----
    checks = []
    if ci:
        thr = g(ci, "thresholds.imbalance_ratio_alert")
        checks.append((f"Class balance ({target})", "medium" if ci_alerts else "ok",
                       f"ratio {ci.get('imbalance_ratio')}" + (f" (alert ≥ {thr:g})" if thr else "")))
    attributes = []
    for attr in (g(FP, "config.protected_attributes") or list(rep.keys())):
        attributes.append(_attribute_block(attr, rep, tba, AIF, FP, di_band, spd_thr, rep_thr, cfg, rows_n))
        a = attributes[-1]
        if a["rep_ratio"] is not None:
            checks.append((f"{attr}: representation", a["rep_sev"], f"ratio {a['rep_ratio']} (alert ≥ {rep_thr:g})"))
        if a["di"] is not None:
            checks.append((f"{attr}: disparate impact", a["di_sev"], f"{a['di']:.3f} (ok {di_band[0]:g}–{di_band[1]:g})"))
        if a["spd"] is not None:
            checks.append((f"{attr}: parity difference", a["spd_sev"], f"{a['spd']:+.3f} (ok |x| < {spd_thr:g})"))
    iedf = g(FP, "aif360_metrics.intersectional")
    if iedf is not None:
        v = g(iedf, "smoothed_edf.value")
        checks.append(("Intersectional EDF", "na" if v is None else "notice",
                       "value = null (not computed)" if v is None else f"{v:.3f} (no threshold)"))

    # ---- overview "what this means" ----
    meaning = []
    if ci and not ci_alerts:
        meaning.append("Your data has about as many rows of each label, so a model will not simply favour one label.")
    elif ci_alerts:
        meaning.append("One label is much rarer than the other, so a model may favour the majority label.")
    for a in attributes:
        if a["di_sev"] == "high" or a["spd_sev"] == "high":
            lo_g, hi_g = a["rate_extremes"]
            meaning.append(f"For {a['name']}, the share of label = 1 ranges from {pct(lo_g[1], 0)} ({lo_g[0]}) to "
                           f"{pct(hi_g[1], 0)} ({hi_g[0]}). A model trained on this data may learn that {a['name']} predicts the label.")
    if n_high:
        meaning.append("Check whether that reflects reality or how the data was collected before using the model for decisions about people.")

    ctx = dict(
        cfg=cfg, C=C,
        meta=dict(dataset_id=meta.get("dataset_id", "—"), version=meta.get("dataset_version", "—"),
                  target=target or "—", created=fmt_time(meta.get("created_at"), cfg.timezone),
                  report_id=meta.get("id", "—")),
        status=status, tiles=tiles, mit_tile=mit_tile, alerts=alerts, checks=checks,
        overview_meaning=" ".join(meaning), notices=notices,
        class_balance=_class_block(ci, target) if ci else None,
        attributes=attributes, rep_thr=rep_thr, di_band=di_band, spd_thr=spd_thr,
        base_rate=next((g(a, "functions.base_rate_overall.value") for a in AIF.values()), None),
        intersection=_intersection_block(inter, cfg),
        edf=[(k, g(a, "functions.smoothed_edf.value")) for k, a in AIF.items()],
        iedf=iedf,
        dq=_dq_block(R, rows_n, mv, dup, od, skew, high_skew, inconsistent, cvc, cfg),
        tech=_tech_block(R, FP, rep, mv, target),
        fp_available=bool(FP),
    )
    ctx["transformation"] = _transformation_block(tmeta, steps, meta, R, ctx, cfg) if steps else None
    ctx["mitigation_without_report"] = bool(mit.get("mitigation_performed")) and not steps
    return ctx


# ----------------------------------------------------------------------------- blocks
def _alert_plain(kind, attr, rep, AIF, tba, di_band, spd_thr) -> Markup:
    r = rep.get(attr) or {}
    f = g(AIF, f"{attr}.functions", {}) or {}
    priv = g(AIF, f"{attr}.privileged_group")
    prate = g(tba, f"{attr}.positive_rate_by_group.{priv}") if priv else None
    if kind == "representation" and r:
        lg, sg = r.get("largest_group"), r.get("smallest_group")
        return (Markup("The largest %s group (%s, %s rows) is %s the smallest (%s, %s rows). "
                       "The model sees few examples of small groups, so its predictions for them are less reliable.")
                % (attr, B(lg), f"{g(r, f'groups.{lg}.count', '?'):,}", B(f"{r.get('max_min_ratio', 0):.0f}×"),
                   B(sg), f"{g(r, f'groups.{sg}.count', '?'):,}"))
    if kind == "disparate_impact":
        di = g(f, "disparate_impact_ratio.value")
        if di is not None:
            extra = (f" (≈{pct(prate * di, 0)} vs {pct(prate, 0)})" if prate is not None else "")
            return (Markup("Rows <b>outside</b> the reference group (%s) have label = 1 about %s as often as %s rows%s. "
                           "The accepted range is %s–%s.") % (priv, B(f"{di:.2f}×"), priv, extra, f"{di_band[0]:g}", f"{di_band[1]:g}"))
    if kind == "statistical_parity":
        spd = g(f, "statistical_parity_difference.value")
        if spd is not None:
            return (Markup("That is a gap of %s in the label = 1 rate (limit: %s points). "
                           "A model trained on this data can learn to use %s as a shortcut.")
                    % (B(f"{abs(spd) * 100:.1f} percentage points"), f"{spd_thr * 100:g}", attr))
    return Markup("See the raw alert below.")


def _class_block(ci, target):
    cc = ci.get("class_counts") or {}
    cp = ci.get("class_percentages") or {}
    items = [(f"{target} = {k}", v) for k, v in cc.items()]
    colors = ([C["c0"], C["c1"]] + [C["c1"]] * len(items))[:len(items)]
    labels = [f"{v:,}" + (f"  ({cp[k]:.2f}%)" if num(cp.get(k)) is not None else "") for k, v in cc.items()]
    chart = charts.hbar(items, w=640, label_w=100, value_w=130, colors=colors, value_labels=labels) if items else ""
    return dict(chart=chart, ratio=ci.get("imbalance_ratio"), thresholds=ci.get("thresholds") or {},
                alerts=ci.get("alerts") or [], pcts=cp, counts=cc, majority=ci.get("majority_label"),
                minority=ci.get("minority_label"))


def _attribute_block(attr, rep, tba, AIF, FP, di_band, spd_thr, rep_thr, cfg, rows_n):
    r = rep.get(attr) or {}
    groups = r.get("groups") or {}
    f = g(AIF, f"{attr}.functions", {}) or {}
    priv = g(AIF, f"{attr}.privileged_group") or g(FP, f"config.privileged_groups.{attr}")
    ratio = r.get("max_min_ratio")
    rep_sev = "ok" if ratio is None or ratio < rep_thr else cfg.severity_by_kind.get("representation", "medium")
    ann = {}
    if r.get("largest_group"): ann[r["largest_group"]] = ("largest", C["mut"])
    if r.get("smallest_group") and ratio is not None:
        ann[r["smallest_group"]] = (f"smallest · {ratio:g}× gap" + (" · OK" if rep_sev == "ok" else ""),
                                    C["ok"] if rep_sev == "ok" else C["high"])
    rep_chart = charts.hbar([(k, v.get("count", 0)) for k, v in groups.items()], w=640, label_w=120, value_w=190,
                            fmt=lambda v: f"{v:,}" + (f"  ({v / rows_n * 100:.1f}%)" if rows_n else ""), annot=ann)
    prb = g(tba, f"{attr}.positive_rate_by_group") or {}
    nmap = {k: v.get("count") for k, v in groups.items()}
    rows_sorted = sorted(prb.items(), key=lambda kv: -kv[1])
    stacked = charts.stacked100(rows_sorted, base=g(f, "base_rate_overall.value"), nmap=nmap, small_n=cfg.small_group_n)
    di = g(f, "disparate_impact_ratio.value")
    spd = g(f, "statistical_parity_difference.value")
    di_flag = di is not None and not (di_band[0] <= di <= di_band[1])
    spd_flag = spd is not None and abs(spd) >= spd_thr
    di_sev = "na" if di is None else (cfg.severity_by_kind["disparate_impact"] if di_flag else "ok")
    spd_sev = "na" if spd is None else (cfg.severity_by_kind["statistical_parity"] if spd_flag else "ok")
    di_hi = max(2.0, (di or 0) * 1.1)
    gauges = dict(
        di=charts.gauge(di, 0.4, di_hi, di_band, ideal=1, ticks=[0.4, 1, round(di_hi, 1)], flagged=di_flag) if di is not None else None,
        spd=charts.gauge(spd, -0.4, 0.4, (-spd_thr, spd_thr), ideal=0, ticks=[-0.4, 0, 0.4], flagged=spd_flag,
                         fmtv=lambda v: f"{v:+.3f}") if spd is not None else None)
    pw = g(AIF, f"{attr}.pairwise_vs_privileged") or []
    pw_rows = sorted([(d.get("unprivileged"), d.get("disparate_impact_ratio"), d.get("n")) for d in pw
                      if num(d.get("disparate_impact_ratio")) is not None], key=lambda r_: -r_[1])
    pw_hi = max([2.0] + [r_[1] * 1.05 for r_ in pw_rows])
    pairwise = charts.dotplot(pw_rows, 0.4, pw_hi, di_band, ref=1, ticks=(0.4, di_band[0], 1, di_band[1], round(pw_hi, 1))) if len(pw_rows) > 1 else ""
    n_out = sum(1 for _, v, _ in pw_rows if not (di_band[0] <= v <= di_band[1]))
    priv_rate = prb.get(priv) if priv else None
    rest_rate = priv_rate * di if (priv_rate is not None and di is not None) else None
    rate_extremes = (rows_sorted[-1], rows_sorted[0]) if rows_sorted else (("—", 0), ("—", 0))
    return dict(name=attr, priv=priv, groups=groups, rep_chart=rep_chart, rep_ratio=ratio, rep_sev=rep_sev,
                largest=r.get("largest_group"), smallest=r.get("smallest_group"), stacked=stacked, prb=prb,
                di=di, spd=spd, di_sev=di_sev, spd_sev=spd_sev, gauges=gauges, pairwise=pairwise,
                pw_rows=pw_rows, n_out=n_out, priv_rate=priv_rate, rest_rate=rest_rate,
                rate_extremes=rate_extremes, edf=g(f, "smoothed_edf.value"),
                small=[k for k, n in nmap.items() if n is not None and n < cfg.small_group_n])


def _intersection_block(inter, cfg):
    attrs = inter.get("attributes") or []
    groups = g(inter, "representation.groups") or {}
    rates = g(inter, "target_by_intersection.positive_rate_by_group") or {}
    if len(attrs) != 2 or not groups:
        return None
    a_vals, b_vals = [], []
    for k in groups:
        parts = [p.strip() for p in k.split("|")]
        if len(parts) != 2: continue
        if parts[0] not in a_vals: a_vals.append(parts[0])
        if parts[1] not in b_vals: b_vals.append(parts[1])
    grid = []
    for a in a_vals:
        row = []
        for b in b_vals:
            k = f"{a} | {b}"
            n = g(groups, f"{k}.count") if k in groups else None
            p = rates.get(k)
            if n is None or p is None:
                row.append(None); continue
            r_ = int(0xF2 + (0x2F - 0xF2) * p); g_ = int(0xF4 + (0x4B - 0xF4) * p); b_ = int(0xF8 + (0x7C - 0xF8) * p)
            row.append(dict(p=p, n=n, low=n < cfg.small_group_n, bg=f"rgb({r_},{g_},{b_})", fg="#fff" if p > 0.55 else C["ink"]))
        grid.append((a, row))
    return dict(attrs=attrs, cols=b_vals, grid=grid, small=g(inter, "representation.groups_under_30") or [],
                n_groups=g(inter, "representation.n_groups"))


def _dq_block(R, rows_n, mv, dup, od, skew, high_skew, inconsistent, cvc, cfg):
    out = {}
    if mv:
        out["missing"] = charts.hbar([(k, v.get("count", 0)) for k, v in mv.items()], w=330, label_w=118, value_w=78,
                                     colors=[C["info"]] * len(mv),
                                     fmt=lambda v: f"{v:,}" + (f" ({v / rows_n * 100:.2f}%)" if rows_n else ""))
        out["missing_cells"] = sum(int(v.get("count", 0)) for v in mv.values())
    if dup is not None and rows_n:
        out["dup"] = dict(n=dup, pct=dup / rows_n * 100, chart=charts.donut(dup, rows_n),
                          samples=len(R.get("sample_duplicate_rows") or []))
    if od:
        out["outliers"] = charts.hbar([(k, v.get("percent", 0)) for k, v in od.items()], w=330, label_w=118, value_w=50,
                                      fmt=lambda v: f"{v:.2f}%",
                                      colors=[C["warn"] if (v.get("percent") or 0) > cfg.outlier_notice_pct else C["c0"] for v in od.values()])
        worst = max(od.items(), key=lambda kv: kv[1].get("percent") or 0)
        out["outliers_worst"] = (worst[0], worst[1].get("percent") or 0)
    if skew:
        items = [(k, abs(v)) for k, v in skew.items()]
        out["skew"] = charts.hbar(items, w=330, label_w=118, value_w=40, fmt=lambda v: f"{v:.2f}",
                                  colors=[C["warn"] if v > cfg.skew_notice_abs else C["c0"] for _, v in items],
                                  ref=(cfg.skew_notice_abs, f"|skew| = {cfg.skew_notice_abs:g} (rule of thumb)"),
                                  maxv=max(5, max(v for _, v in items)))
        out["high_skew"] = high_skew
    if cvc:
        out["categorical"] = []
        for c, vc in cvc.items():
            items = list(vc.items())[:12]
            out["categorical"].append(dict(col=c, inconsistent=c in inconsistent,
                                           chart=charts.hbar(items, w=330, label_w=70, value_w=50, fmt=lambda v: f"{v:,}",
                                                             colors=[C["na"] if str(k) in ("None", "nan") else C["c1"] for k, _ in items])))
    cm = R.get("correlation_matrix") or {}
    if cm:
        cols = list(cm.keys())
        out["corr"] = charts.corr_heatmap(cols, cm, w=360)
        target = R.get("target_column")
        offs = [abs(cm[a][b]) for a in cols for b in cols if a < b and a != target and b != target and num(cm[a].get(b)) is not None]
        tcorr = [abs(cm[target][c]) for c in cols if target in cm and c != target and num(cm[target].get(c)) is not None]
        out["corr_max_pair"] = max(offs) if offs else None
        out["corr_max_target"] = max(tcorr) if tcorr else None
    return out


def _tech_block(R, FP, rep, mv, target):
    ss = R.get("summary_statistics") or {}
    ds = R.get("distribution_statistics") or {}
    stats = []
    for k, s in ss.items():
        d = ds.get(k, {})
        stats.append([k] + [fmt_value(s.get(x)) for x in ("count", "mean", "std", "min", "25%", "50%", "75%", "max")]
                     + [fmt_value(d.get("skew")), fmt_value(d.get("kurtosis"))])
    cols = []
    uv = R.get("unique_values") or {}
    prot = g(FP, "config.protected_attributes") or []
    for c in R.get("columns") or []:
        u = uv.get(c)
        star = False
        if u is None and c in rep:
            u, star = rep[c].get("n_groups"), True
        cols.append(dict(name=c, dtype=(R.get("dtypes") or {}).get(c, "—"), unique="—" if u is None else f"{u}{'*' if star else ''}",
                         missing=(mv.get(c) or {}).get("count", 0),
                         role="target" if c == target else ("protected" if c in prot else "")))
    dups = R.get("sample_duplicate_rows") or []
    cfgp = FP.get("config") or {}
    kv = []
    if cfgp:
        kv += [("Protected attributes", ", ".join(cfgp.get("protected_attributes") or [])),
               ("Privileged groups", ", ".join(f"{k} = {v}" for k, v in (cfgp.get("privileged_groups") or {}).items())),
               ("Detection source", str(cfgp.get("source", "—"))), ("Positive label", str(cfgp.get("pos_label", "—"))),
               ("Fairness mode", str(cfgp.get("fairness_mode", "—")))]
    if g(FP, "aif360_metrics.api"): kv.append(("Metric library", g(FP, "aif360_metrics.api")))
    if R.get("data_drift") is not None: kv.append(("data_drift", fmt_value(R.get("data_drift"))))
    if g(FP, "aif360_metrics.note"): kv.append(("Note", g(FP, "aif360_metrics.note")))
    return dict(stats=stats, cols=cols, dups=[{k: fmt_value(v) for k, v in r.items()} for r in dups[:10]], kv=kv)


def _transformation_block(tmeta, steps, bmeta, R, ctx, cfg):
    def status(t): return cfg.step_status.get(t, "applied")
    def name(t): return cfg.step_names.get(t, t.replace("_", " ").capitalize())
    def orig(r): return r.get("original_value", r.get("original_missing_values"))   # field-name inconsistency
    order: List[str] = []
    for r in steps:
        t = r.get("transformation", "unknown")
        if t not in order: order.append(t)
    timeline = []
    for i, t in enumerate(order):
        rs = [r for r in steps if r.get("transformation") == t]
        cols = list(dict.fromkeys(str(r.get("column")) for r in rs))
        timeline.append(dict(idx=i + 1, type=t, name=name(t), status=status(t), n=len(rs), cols=", ".join(cols)))
    step_no = {t["type"]: t["idx"] for t in timeline}
    counts = {s: sum(status(r.get("transformation", "")) == s for r in steps) for s in ("applied", "skipped", "info")}
    by = lambda t: [r for r in steps if r.get("transformation") == t]

    # bias finding -> step link table
    links = []
    mc = ctx["dq"].get("missing_cells")
    if mc:
        links.append((f"{mc:,} missing cells", f"{step_no['missing_value_fill']}. {name('missing_value_fill')}" if "missing_value_fill" in step_no else "—",
                      "ok" if "missing_value_fill" in step_no else "medium"))
    dup = R.get("duplicate_rows_count")
    if dup:
        links.append((f"{dup:,} duplicate rows", f"{step_no['duplicate_removal']}. {name('duplicate_removal')}" if "duplicate_removal" in step_no else "—",
                      "ok" if "duplicate_removal" in step_no else "medium"))
    hs = ctx["dq"].get("high_skew") or []
    if hs:
        fixed = {r.get("column") for r in by("skew_correction")}
        links.append((f"Strongly skewed (|skew| > {cfg.skew_notice_abs:g}): {', '.join(hs)}",
                      f"{step_no['skew_correction']}. {name('skew_correction')}" if "skew_correction" in step_no else "—",
                      "ok" if set(hs) <= fixed else ("na" if fixed else "medium")))
    for c in [c["col"] for c in ctx["dq"].get("categorical", []) if c["inconsistent"]]:
        sk = [r for r in steps if r.get("column") == c and r.get("transformation") not in ("missing_value_fill",)]
        links.append((f"{c}: inconsistent spellings", ", ".join(f"{step_no[r['transformation']]}. {name(r['transformation'])}" for r in sk) or "—",
                      "na" if sk else "medium"))
    fair_steps = [r for r in steps if r.get("transformation") in cfg.fairness_step_types]
    for a in ctx["alerts"]:
        links.append((f"{a['attr']}: {a['short']}", ", ".join(name(r['transformation']) for r in fair_steps) or "—",
                      "ok" if fair_steps else a["sev"]))
    unaddressed_fairness = not fair_steps and any(a["kind"] in ("disparate_impact", "statistical_parity", "representation") for a in ctx["alerts"])

    mv = R.get("missing_values") or {}
    fills = [dict(col=r.get("column"), method=r.get("method"), before=fmt_value(orig(r)),
                  fill=fmt_value(r.get("modified_value")), full=(mv.get(r.get("column")) or {}).get("count"))
             for r in by("missing_value_fill")]
    rep = (R.get("fairness_profile") or {}).get("representation") or {}
    enc = [dict(col=r.get("column"), method=r.get("method"), before=fmt_value(orig(r)), after=fmt_value(r.get("modified_value")),
                pills=[f"{r.get('column')}_{str(k).replace(' ', '_')}" for k in (rep.get(r.get("column")) or {}).get("groups", {})])
           for r in by("encoding")]
    skew_rows = [(r.get("column"), orig(r), r.get("modified_value")) for r in by("skew_correction")
                 if num(orig(r)) is not None and num(r.get("modified_value")) is not None]
    ovs = []
    for r in by("oversampling_skipped") + by("oversampling"):
        o = orig(r)
        chart = None
        if isinstance(o, dict) and all(num(v) is not None for v in o.values()):
            chart = charts.hbar([(f"label = {k}", v) for k, v in o.items()], w=330, label_w=62, value_w=40,
                                colors=[C["c0"], C["c1"]][:len(o)] + [C["c1"]] * max(0, len(o) - 2))
        tot = sum(o.values()) if isinstance(o, dict) and all(num(v) is not None for v in o.values()) else None
        ovs.append(dict(status=status(r.get("transformation")), counts=o if isinstance(o, dict) else None, chart=chart,
                        text=fmt_value(r.get("modified_value")), total=tot,
                        min_maj=(min(o.values()) / max(o.values())) if tot else None))
    known = {"missing_value_fill", "duplicate_removal", "encoding", "encoding_skipped", "task_inference",
             "skew_correction", "oversampling_skipped", "oversampling", "drift_mitigation"}
    other = [dict(col=r.get("column"), t=r.get("transformation"), method=r.get("method"), before=fmt_value(orig(r)),
                  after=fmt_value(r.get("modified_value"))) for r in steps if r.get("transformation") not in known]
    raw = [dict(i=i + 1, col=r.get("column"), t=r.get("transformation"), method=r.get("method"),
                before=fmt_value(orig(r)), after=fmt_value(r.get("modified_value"))) for i, r in enumerate(steps)]
    simple = lambda t: [dict(col=r.get("column"), method=r.get("method"), before=fmt_value(orig(r)), after=fmt_value(r.get("modified_value"))) for r in by(t)]
    return dict(
        meta=dict(dataset_id=tmeta.get("dataset_id", bmeta.get("dataset_id", "—")), version=tmeta.get("version", "—"),
                  from_version=bmeta.get("dataset_version", "—"), report_id=tmeta.get("id", "—"),
                  created=fmt_time(tmeta.get("created_at"), cfg.timezone)),
        total=len(steps), counts=counts, timeline=timeline, links=links, unaddressed_fairness=unaddressed_fairness,
        fills=fills, dups=simple("duplicate_removal"), enc=enc, enc_skipped=simple("encoding_skipped"),
        task=simple("task_inference"), skew=charts.dumbbell(skew_rows) if skew_rows else "", ovs=ovs,
        drift=simple("drift_mitigation"), drift_all_zero=all(orig(r) in (0, 0.0) and r.get("modified_value") in (0, 0.0) for r in by("drift_mitigation")),
        other=other, raw=raw, step_no=step_no, rows=R.get("shape", [None])[0],
    )
