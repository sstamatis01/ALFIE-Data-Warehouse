"""Model bias (Aequitas audit) -> render context. All JSON paths for the model section live here.

Input: the stored audit document (ModelBiasAuditResponse as dict, collection `model_bias_audits`)
or just its inner `report` ({metrics, disparities, performance, alerts}).

Rules:
* Never invent numbers. Group sizes are DERIVED exactly like model_bias_alerts._group_sizes:
  n = round(performance.pp * ppr / pprev). Groups with pprev = 0 get n = None ("not available").
* Pass/fail per cell mirrors model_bias_alerts.build_model_bias_alerts so the PDF never disagrees
  with the stored alerts: outside the band + group n >= 30 + metric in model_alert_metrics
  (+ selection-rate gap >= 0.1) -> High. Other out-of-band cells -> Notice (shown, not alerted).
  Groups under 30 rows -> greyed ("few rows"), never alerted.
* The band comes from the alert strings ("outside [0.8, 1.25]") and falls back to ReportConfig.
* Aequitas significance flags are shown as a marker only; they do not change the verdict.
"""
from __future__ import annotations
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from markupsafe import Markup

from . import charts
from .config import MODEL_METRICS, PALETTE as C, ReportConfig
from .context import B, build_context, fmt_time, g, num

pct = charts.pct

_RATE_RE = re.compile(
    r"^(?P<attr>[^:]+):\s+(?P<group>.+?)\s+(?P<label>selection rate|true-positive rate|false-positive rate)\s+"
    r"(?P<ratio>[\d.]+)\s+times\s+(?P<ref>.+?),\s+outside\s+\[(?P<lo>[\d.]+),\s*(?P<hi>[\d.]+)\]")
_LABEL_TO_METRIC = {"selection rate": "pprev", "true-positive rate": "tpr", "false-positive rate": "fpr"}


def normalise_audit(doc: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if isinstance(doc, dict) and isinstance(doc.get("report"), dict) and "metrics" in doc["report"]:
        return doc, doc["report"]
    return {}, doc or {}


def _alerts(meta, rep) -> List[str]:
    out: List[str] = []
    for a in (meta.get("alerts") or []) + (rep.get("alerts") or []):   # stored twice today; de-duplicate
        if isinstance(a, str) and a not in out:
            out.append(a)
    return out


def build_model_bias_context(audit_doc: Dict[str, Any], bias_doc: Optional[Dict[str, Any]] = None,
                             cfg: Optional[ReportConfig] = None) -> Dict[str, Any]:
    cfg = cfg or ReportConfig()
    meta, R = normalise_audit(audit_doc)
    metrics = [m for m in (R.get("metrics") or []) if m.get("attribute_name") is not None]
    disp = {(str(d.get("attribute_name")), str(d.get("attribute_value"))): d for d in (R.get("disparities") or [])}
    mrow = {(str(m.get("attribute_name")), str(m.get("attribute_value"))): m for m in metrics}
    perf = next((p for p in (R.get("performance") or [])
                 if p.get("attribute_value") == "all" or p.get("attribute_name") == "group_performance"), {})
    alerts_raw = _alerts(meta, R)

    m = next((_RATE_RE.search(a) for a in alerts_raw if _RATE_RE.search(a)), None)
    band = (float(m.group("lo")), float(m.group("hi"))) if m else cfg.model_fair_band
    attrs = list(meta.get("protected_attributes") or dict.fromkeys(str(x.get("attribute_name")) for x in metrics))
    refs: Dict[str, str] = dict(meta.get("reference_groups") or {})
    for a in attrs:   # fall back: the group whose disparities are all exactly 1
        if a not in refs:
            refs[a] = next((gv for (an, gv), d in disp.items() if an == a and
                            all(v == 1 for k, v in d.items() if k.endswith("_disparity"))), "")

    pp = num(perf.get("pp"))

    def size(row) -> Optional[int]:
        ppr, pprev = num(row.get("ppr")), num(row.get("pprev"))
        if pp is None or ppr is None or not pprev:
            return None
        return int(round(pp * ppr / pprev))

    sizes = {k: size(r) for k, r in mrow.items()}
    small = {k for k, n in sizes.items() if n is not None and n < cfg.model_min_group}

    def cell_status(attr, group, metric) -> Tuple[str, Optional[float]]:
        if group == refs.get(attr):
            return "ref", 1.0
        d = num((disp.get((attr, group)) or {}).get(f"{metric}_disparity"))
        if d is None:
            return "na", None
        if band[0] <= d <= band[1]:
            return "ok", d
        if (attr, group) in small:
            return "small", d
        if metric in cfg.model_alert_metrics:
            if metric == "pprev":
                gr, rr = num(mrow.get((attr, group), {}).get("pprev")), num(mrow.get((attr, refs.get(attr)), {}).get("pprev"))
                if gr is None or rr is None or abs(gr - rr) < cfg.model_pprev_min_gap:
                    return "notice", d
            return "high", d
        return "notice", d

    # ---------------- per attribute ----------------
    attributes = []
    for a in attrs:
        ref = refs.get(a, "")
        groups = [str(r.get("attribute_value")) for r in metrics if str(r.get("attribute_name")) == a]
        groups.sort(key=lambda gv: (gv != ref, -(sizes.get((a, gv)) or 0)))
        if not groups:
            continue
        n_items = [(gv, sizes.get((a, gv)) or 0) for gv in groups]
        size_labels = []
        for gv in groups:
            n = sizes.get((a, gv)); prev = num(mrow[(a, gv)].get("prev"))
            size_labels.append("—" if n is None else f"{n:,}" + (f"  ({round(n * prev):,} actual positives)" if prev is not None else ""))
        size_chart = charts.hbar(n_items, w=640, label_w=130, value_w=200, bar_h=13, gap=5,
                                 colors=[C["na"] if (a, gv) in small else (C["c1"] if gv == ref else C["c0"]) for gv in groups],
                                 value_labels=size_labels,
                                 annot={gv: ("reference" if gv == ref else f"< {cfg.model_min_group} rows", C["mut"] if gv == ref else C["high"])
                                        for gv in groups if gv == ref or (a, gv) in small})
        shift = charts.rate_shift([(gv, num(mrow[(a, gv)].get("prev")), num(mrow[(a, gv)].get("pprev")), sizes.get((a, gv)),
                                    gv == ref, (a, gv) in small) for gv in groups])
        disparity_charts = []
        for metric in cfg.model_alert_metrics:
            rows = []
            rr = num(mrow.get((a, ref), {}).get(metric))
            for gv in groups:
                st, d = cell_status(a, gv, metric)
                gr = num(mrow[(a, gv)].get(metric))
                note = ("reference" + (f" · {pct(gr, 0)}" if gr is not None else "")) if st == "ref" else (
                    "—" if d is None else f"{d:.2f}×" + (f" · {pct(gr, 0)} vs {pct(rr, 0)}" if gr is not None and rr is not None else ""))
                rows.append((gv + (" ⚠" if st == "small" else ""), d, st, note))
            n_high = sum(r[2] == "high" for r in rows)
            kind = MODEL_METRICS[metric][1]
            dir_notes = []
            for gv in groups:
                st, d = cell_status(a, gv, metric)
                if st != "high" or d is None or kind == "neutral":
                    continue
                worse = gv if (d > 1) == (kind == "error") else ref
                verb = {"fpr": "wrongly predicted as 1", "tpr": "missed (true 1 predicted as 0)"}.get(metric, "worse off")
                dir_notes.append(f"{gv} vs {ref}: {worse} rows are {verb} more often.")
            disparity_charts.append(dict(metric=metric, name=MODEL_METRICS[metric][0], kind=MODEL_METRICS[metric][1],
                                         chart=charts.disparity_bars(rows, band), n_high=n_high, dir_notes=dir_notes,
                                         n_small_out=sum(r[2] == "small" for r in rows)))
        matrix = []
        for metric in cfg.model_matrix_metrics:
            cells = []
            for gv in groups:
                st, d = cell_status(a, gv, metric)
                sig = bool((disp.get((a, gv)) or {}).get(f"{metric}_significance"))
                cells.append(dict(st=st, d=d, sig=sig))
            matrix.append(dict(metric=metric, name=MODEL_METRICS[metric][0], kind=MODEL_METRICS[metric][1], cells=cells))
        rates = [dict(group=gv, ref=gv == ref, small=(a, gv) in small, n=sizes.get((a, gv)),
                      vals={k: num(mrow[(a, gv)].get(k)) for k in ("accuracy", "prev", "pprev", "tpr", "fpr", "fnr", "precision", "ppr")})
                 for gv in groups]
        high_cells = [(gv, row["metric"], c["d"]) for row in matrix for gv, c in zip(groups, row["cells"]) if c["st"] == "high"]
        attributes.append(dict(name=a, ref=ref, groups=groups, size_chart=size_chart, shift=shift,
                               disparity=disparity_charts, matrix=matrix, rates=rates, high_cells=high_cells,
                               small=[(gv, sizes.get((a, gv))) for gv in groups if (a, gv) in small],
                               n_notice=sum(c["st"] == "notice" for row in matrix for c in row["cells"])))

    # ---------------- alerts in plain language ----------------
    alerts = []
    for a in alerts_raw:
        mm = _RATE_RE.search(a)
        if mm:
            attr, grp, ref, ratio = mm.group("attr").strip(), mm.group("group").strip(), mm.group("ref").strip(), float(mm.group("ratio"))
            metric = _LABEL_TO_METRIC[mm.group("label")]
            gr, rr = num(mrow.get((attr, grp), {}).get(metric)), num(mrow.get((attr, ref), {}).get(metric))
            plain = _rate_plain(metric, attr, grp, ref, ratio, gr, rr, mrow)
            alerts.append(dict(sev=cfg.model_alert_severity["rate"], attr=attr, plain=plain, raw=a, kind="rate"))
        elif "fewer than" in a:
            attr = a.split(":", 1)[0].strip()
            lst = ", ".join(f"{gv} (n={n})" for gv, n in next((x["small"] for x in attributes if x["name"] == attr), []))
            plain = Markup("Some %s groups are too small to judge: %s. One or two rows can swing their rates a lot, so they "
                           "are shown greyed and not alerted.") % (attr, lst or "see raw alert")
            alerts.append(dict(sev=cfg.model_alert_severity["small_groups"], attr=attr, plain=plain, raw=a, kind="small"))
        else:
            alerts.append(dict(sev=cfg.model_alert_severity["other"], attr=a.split(":", 1)[0] if ":" in a else "",
                               plain=Markup("See the raw alert below."), raw=a, kind="other"))
    alerts.sort(key=lambda x: {"high": 0, "medium": 1}.get(x["sev"], 2))
    n_high = sum(x["sev"] == "high" for x in alerts)
    n_med = sum(x["sev"] == "medium" for x in alerts)
    n_notice = sum(x["n_notice"] for x in attributes)

    hi_attrs = list(dict.fromkeys(x["attr"] for x in alerts if x["sev"] == "high"))
    if n_high:
        status = dict(level="high", icon="✕", title=Markup("Needs attention: the model treats ") +
                      Markup(" and ").join(Markup("<u>%s</u>") % x for x in hi_attrs) + Markup(" groups differently"))
    elif n_med:
        status = dict(level="medium", icon="▲", title=Markup("Review recommended: %d caution(s)") % n_med)
    else:
        status = dict(level="ok", icon="✓", title=Markup("No model bias alerts raised"))
    n_rows = meta.get("n_rows") or perf.get("total_entities")
    acc = num(perf.get("accuracy"))
    sub = []
    if n_rows:
        sub.append(f"Checked on {n_rows:,} rows" + (f" of the {meta['eval_split']} split" if meta.get("eval_split") else "")
                   + (f" (dataset {meta['dataset_version']})" if meta.get("dataset_version") else "") + ".")
    if acc is not None:
        sub.append(f"Overall accuracy {pct(acc)}.")
    quiet = [a for a in attrs if a not in hi_attrs]
    if quiet and n_high:
        sub.append(f"No rate alert for {', '.join(quiet)}.")
    status["subtitle"] = " ".join(sub)
    status["counts"] = [("high", n_high), ("medium", n_med), ("notice", n_notice)]

    notes = [x for x in (meta.get("notes") or []) if isinstance(x, str)]
    thr = None
    for x in notes:
        mt = re.search(r"probability at least (\d+(?:\.\d+)?)", x)
        if mt:
            thr = mt.group(1)
    tiles = [
        ("Rows checked", f"{n_rows:,}" if n_rows else "—",
         " · ".join(x for x in [f"{meta.get('eval_split')} split" if meta.get("eval_split") else "",
                                f"dataset {meta.get('dataset_version')}" if meta.get("dataset_version") else ""] if x)),
        ("Overall accuracy", pct(acc) if acc is not None else "—", ""),
        ("Predicted positive", pct(num(perf.get("pprev"))) if num(perf.get("pprev")) is not None else "—",
         f"actual positive rate {pct(num(perf.get('prev')))}" if num(perf.get("prev")) is not None else ""),
        ("Protected attributes", str(len(attrs)), ", ".join(attrs)),
        ("Positive call", f"score ≥ {thr}" if thr else "—", f"label {meta.get('positive_label')} = positive" if meta.get("positive_label") else ""),
    ]

    meaning = []
    for x in attributes:
        if x["high_cells"]:
            gs = list(dict.fromkeys(gv for gv, _, _ in x["high_cells"]))
            meaning.append(f"For {x['name']}, the model treats {', '.join(gs)} differently from {x['ref']} "
                           f"(outside the accepted {band[0]:g}–{band[1]:g}× range).")
    if any(x["small"] for x in attributes):
        meaning.append(f"Groups with fewer than {cfg.model_min_group} test rows cannot be judged yet and need more test data.")
    if n_high:
        meaning.append("Before the model is used for decisions about people, check whether these differences are justified; "
                       "options are re-training on more balanced data or a different decision threshold.")
    elif not alerts:
        meaning.append("Selection and error rates stay within the accepted range for every group large enough to judge.")

    overall = None
    if perf:
        cm = {k: perf.get(k) for k in ("tp", "fp", "fn", "tn")}
        overall = dict(
            confusion=charts.confusion(*(int(cm[k]) for k in ("tp", "fp", "fn", "tn"))) if all(isinstance(v, (int, float)) for v in cm.values()) else "",
            bars=charts.hbar([(MODEL_METRICS[k][0], num(perf.get(k))) for k in ("accuracy", "tpr", "tnr", "precision", "fpr", "fnr")
                              if num(perf.get(k)) is not None], w=330, label_w=118, value_w=46, maxv=1,
                             fmt=lambda v: pct(v, 0),
                             colors=[C["c1"]] * 4 + [C["c0"]] * 2),
            pp=perf.get("pp"), pn=perf.get("pn"), pos=perf.get("group_label_pos"), neg=perf.get("group_label_neg"))

    # ---------------- link to the dataset bias report ----------------
    link = None
    if bias_doc:
        dctx = build_context(bias_doc, None, cfg)
        rows = []
        for x in attributes:
            da = next((d for d in dctx["attributes"] if d["name"] == x["name"]), None)
            if not da:
                continue
            d_flag = "high" in (da["di_sev"], da["spd_sev"])
            pprev_high = [c for c in x["high_cells"] if c[1] == "pprev"]
            m_flag = bool(x["high_cells"])
            if d_flag and pprev_high:
                st = ("high", "Persists in model")
            elif d_flag and m_flag:
                st = ("high", "Different form in model")
            elif d_flag:
                st = ("ok", "Not seen in model")
            elif m_flag:
                st = ("high", "New in model")
            else:
                st = ("ok", "OK in both")
            dtxt = (f"DI {da['di']:.2f}, parity diff. {da['spd']:+.2f}" if da["di"] is not None and da["spd"] is not None else "—")
            mtxt = "; ".join(f"{gv} {MODEL_METRICS[mt][0].lower()} {d:.2f}×" for gv, mt, d in x["high_cells"]) or "no rate alert"
            rows.append(dict(attr=x["name"], dataset=dtxt, dsev="high" if d_flag else "ok", model=mtxt, st=st))
        link = dict(rows=rows, dataset_version=dctx["meta"]["version"], model_version=meta.get("dataset_version", "—"))

    # ---------------- caveats (data-driven) ----------------
    caveats = []
    sm = [f"{gv} (n={n})" for x in attributes for gv, n in x["small"]]
    if sm:
        caveats.append(f"Small groups: {', '.join(sm)} have fewer than {cfg.model_min_group} test rows. Their ratios are shown but not judged.")
    if metrics and not any("group_size" in r for r in metrics):
        caveats.append("Group sizes are derived (positive predictions × share ÷ selection rate) because the stored group metrics "
                       "have no counts. Storing Aequitas' group_size, tp/fp/fn/tn per group would make them exact.")
    hc = [(x["name"], gv, mt) for x in attributes for gv, mt, _ in x["high_cells"]]
    if hc:
        sig = [h for h in hc if (disp.get((h[0], h[1])) or {}).get(f"{h[2]}_significance")]
        caveats.append(f"Aequitas marks {len(sig)} of {len(hc)} alerted differences as statistically significant (marked • in the matrix). "
                       "The alerts are based on the size of the ratio, not on significance.")
    if any("pprev" == mt for _, _, mt in hc):
        caveats.append("Whether a higher selection rate helps or harms a group depends on what label = 1 means for people; "
                       "the report does not know, so it only says higher or lower.")
    if bias_doc and link and link["dataset_version"] != link["model_version"]:
        caveats.append(f"The dataset bias report describes version {link['dataset_version']}; the model was checked on "
                       f"version {link['model_version']} (after mitigation).")
    ca = meta.get("created_at")
    if (isinstance(ca, str) and not re.search(r"(Z|[+-]\d\d:?\d\d)$", ca)) or (isinstance(ca, datetime) and ca.tzinfo is None):
        caveats.append(f"The audit timestamp is stored without a time zone; it is read as UTC and shown in {cfg.timezone}.")

    return dict(
        meta=dict(model_id=meta.get("model_id", "—"), model_version=meta.get("model_version", "—"),
                  dataset_id=meta.get("dataset_id", "—"), dataset_version=meta.get("dataset_version", "—"),
                  split=meta.get("eval_split") or "—", scorer=meta.get("scorer", "—"), label_mode=meta.get("label_mode", "—"),
                  positive_label=meta.get("positive_label", "—"), audit_id=meta.get("id", "—"), n_rows=n_rows,
                  created=fmt_time(meta.get("created_at"), cfg.timezone)),
        status=status, tiles=tiles, alerts=alerts, meaning=" ".join(meaning), band=band, attributes=attributes,
        overall=overall, link=link, caveats=caveats, notes=notes, perf=perf,
        glossary=[(k, *MODEL_METRICS[k]) for k in list(cfg.model_matrix_metrics) + ["ppr"]],
        tech_metrics=[dict(attr=str(r.get("attribute_name")), group=str(r.get("attribute_value")),
                           n=sizes.get((str(r.get("attribute_name")), str(r.get("attribute_value")))),
                           vals=[num(r.get(k)) for k in ("accuracy", "prev", "pprev", "ppr", "tpr", "tnr", "fpr", "fnr", "precision", "fdr", "for", "npv")])
                      for r in metrics],
        tech_disp=[dict(attr=k[0], group=k[1], vals=[num(d.get(f"{mt}_disparity")) for mt in ("pprev", "ppr", "tpr", "tnr", "fpr", "fnr", "precision", "fdr", "for", "npv")],
                        sig=[bool(d.get(f"{mt}_significance")) for mt in ("pprev", "ppr", "tpr", "tnr", "fpr", "fnr", "precision", "fdr", "for", "npv")])
                   for k, d in disp.items()],
        available=bool(metrics),
    )


def _rate_plain(metric, attr, grp, ref, ratio, gr, rr, mrow) -> Markup:
    rates = (Markup(" (%s vs %s)") % (pct(gr, 0), pct(rr, 0))) if gr is not None and rr is not None else Markup("")
    if metric == "pprev":
        ga = num(mrow.get((attr, grp), {}).get("prev")); ra = num(mrow.get((attr, ref), {}).get("prev"))
        extra = (Markup(" In the test labels the actual positive rates are %s vs %s, so the model %s the gap.")
                 % (pct(ga, 0), pct(ra, 0), "widens" if (ra and ga and abs(ratio - 1) > abs(ga / ra - 1)) else "does not widen")) if ga is not None and ra else Markup("")
        return (Markup("The model predicts label = 1 for %s rows %s as often as for %s rows%s.") % (grp, B(f"{ratio:.2f}×"), ref, rates)) + extra
    if metric == "fpr":
        who = grp if ratio > 1 else ref
        return Markup("Among rows whose true label is 0, %s rows are wrongly predicted as 1 %s as often as %s rows%s. "
                      "%s rows are wrongly flagged more often.") % (grp, B(f"{ratio:.2f}×"), ref, rates, who)
    if metric == "tpr":
        who = grp if ratio < 1 else ref
        return Markup("Among rows whose true label is 1, the model catches %s rows %s as often as %s rows%s. "
                      "%s rows are missed more often.") % (grp, B(f"{ratio:.2f}×"), ref, rates, who)
    return Markup("See the raw alert below.")
