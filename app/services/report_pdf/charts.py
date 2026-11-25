"""Hand-written inline SVG charts (no plotting dependency). Every function returns an SVG
string; the template inserts it with |safe. Only SVG features WeasyPrint renders are used
(rect, line, circle, path, text, pattern)."""
from __future__ import annotations
import math
from html import escape as E
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from .config import PALETTE as C
import itertools
_ids = itertools.count(1)

FONT = "'AutoDW Inter', 'DejaVu Sans', sans-serif"


def _svg(w: float, h: float, body: str) -> str:
    return (f'<svg viewBox="0 0 {w:.0f} {h:.0f}" width="100%" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="{FONT}">{body}</svg>')


def _t(x, y, s, size=11, anchor="start", col=None, w=400) -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
            f'fill="{col or C["ink"]}" font-weight="{w}">{E(str(s))}</text>')


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


# --------------------------------------------------------------------------- bars
def hbar(items: Sequence[Tuple[str, float]], *, w=640, label_w=120, value_w=90, bar_h=18, gap=7,
         maxv: Optional[float] = None, fmt: Callable = lambda v: f"{v:,}", colors=None,
         annot: Optional[Dict[str, Tuple[str, str]]] = None, ref: Optional[Tuple[float, str]] = None,
         value_labels: Optional[Sequence[str]] = None) -> str:
    """Horizontal bar chart. annot = {label: (text, colour)} printed right-aligned."""
    if not items:
        return ""
    maxv = maxv or max(v for _, v in items) or 1
    pw = w - label_w - value_w
    h = len(items) * (bar_h + gap) + 10
    o = ""
    if ref:
        rx = label_w + pw * ref[0] / maxv
        o += f'<line x1="{rx:.1f}" x2="{rx:.1f}" y1="0" y2="{h - 6}" stroke="{C["mut"]}" stroke-dasharray="3 3"/>'
    for i, (k, v) in enumerate(items):
        y = i * (bar_h + gap) + 4
        col = colors[i] if colors else C["c1"]
        bw = max(pw * min(v, maxv) / maxv, 1.5)
        o += _t(label_w - 8, y + bar_h * 0.72, k, 11, "end")
        o += f'<rect x="{label_w}" y="{y}" width="{bw:.1f}" height="{bar_h}" rx="3" fill="{col}"/>'
        o += _t(label_w + bw + 6, y + bar_h * 0.72, value_labels[i] if value_labels else fmt(v), 10.5, col=C["mut"])
        if annot and k in annot:
            txt, acol = annot[k]
            o += _t(w - 2, y + bar_h * 0.72, txt, 10, "end", acol, 600)
    if ref:
        o += _t(label_w + pw * ref[0] / maxv + 4, h + 4, ref[1], 9.5, col=C["mut"])
    return _svg(w, h + (8 if ref else 0), o)


def stacked100(rows: Sequence[Tuple[str, float]], *, base: Optional[float], nmap: Dict[str, int],
               small_n: int = 30, w=640, label_w=150, bar_h=18, gap=7) -> str:
    """100 % stacked bar per group: share of label=0 (light) vs label=1 (dark)."""
    if not rows:
        return ""
    pw = w - label_w - 120
    h = len(rows) * (bar_h + gap) + 34
    hid = f"hatch{next(_ids)}"
    o = (f'<defs><pattern id="{hid}" width="6" height="6" patternUnits="userSpaceOnUse" '
         'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#fff" stroke-width="2"/></pattern></defs>')
    for i, (k, p) in enumerate(rows):
        y = i * (bar_h + gap) + 18
        n = nmap.get(k)
        low = n is not None and n < small_n
        o += _t(label_w - 8, y + bar_h * 0.72, k, 11, "end", C["mut"] if low else None)
        op = "0.45" if low else "1"
        o += (f'<g opacity="{op}"><rect x="{label_w}" y="{y}" width="{pw * (1 - p):.1f}" height="{bar_h}" fill="{C["c0"]}"/>'
              f'<rect x="{label_w + pw * (1 - p):.1f}" y="{y}" width="{pw * p:.1f}" height="{bar_h}" fill="{C["c1"]}"/></g>')
        if low:
            o += f'<rect x="{label_w}" y="{y}" width="{pw}" height="{bar_h}" fill="url(#{hid})"/>'
        o += _t(label_w + pw + 6, y + bar_h * 0.72, pct(p), 10.5, w=600)
        if n is not None:
            o += _t(w - 2, y + bar_h * 0.72, f"n={n}", 9.5, "end", C["high"] if low else C["mut"], 600 if low else 400)
    if base is not None:
        bx = label_w + pw * (1 - base)
        o += f'<line x1="{bx:.1f}" x2="{bx:.1f}" y1="12" y2="{h - 14}" stroke="{C["ink"]}" stroke-width="1.4" stroke-dasharray="4 3"/>'
        o += _t(bx, 9, f"overall label=1 rate {pct(base)}", 9.5, "middle", C["ink"], 600)
    o += f'<rect x="{label_w}" y="{h - 10}" width="10" height="10" fill="{C["c0"]}"/>' + _t(label_w + 14, h - 1, "label = 0", 9.5, col=C["mut"])
    o += f'<rect x="{label_w + 80}" y="{h - 10}" width="10" height="10" fill="{C["c1"]}"/>' + _t(label_w + 94, h - 1, "label = 1 (positive label)", 9.5, col=C["mut"])
    return _svg(w, h, o)


# --------------------------------------------------------------------------- gauges
def gauge(value: float, lo: float, hi: float, band: Tuple[float, float], *, ideal=None, ticks=(),
          flagged=False, fmtv: Callable = lambda v: f"{v:.3f}", w=300, h=62) -> str:
    pad = 14
    pw = w - 2 * pad
    X = lambda v: pad + pw * (min(max(v, lo), hi) - lo) / (hi - lo)
    o = f'<rect x="{pad}" y="24" width="{pw}" height="12" rx="6" fill="#F3E3DA"/>'
    o += (f'<rect x="{X(band[0]):.1f}" y="24" width="{X(band[1]) - X(band[0]):.1f}" height="12" '
          f'fill="{C["band"]}" stroke="{C["ok"]}" stroke-width="1"/>')
    for b in band:
        o += f'<line x1="{X(b):.1f}" x2="{X(b):.1f}" y1="20" y2="40" stroke="{C["ok"]}" stroke-width="1.5"/>'
        o += _t(X(b), 52, f"{b:g}", 9, "middle", C["ok"], 600)
    if ideal is not None:
        o += f'<line x1="{X(ideal):.1f}" x2="{X(ideal):.1f}" y1="24" y2="36" stroke="{C["mut"]}" stroke-dasharray="2 2"/>'
    for tk in ticks:
        o += _t(X(tk), 52, f"{tk:g}", 9, "middle", C["mut"])
    col = C["high"] if flagged else C["ok"]
    x = X(value)
    o += (f'<path d="M{x - 6:.1f},12 L{x + 6:.1f},12 L{x:.1f},22 Z" fill="{col}"/>'
          f'<line x1="{x:.1f}" x2="{x:.1f}" y1="22" y2="38" stroke="{col}" stroke-width="2.5"/>')
    o += _t(min(max(x, 30), w - 30), 9, fmtv(value), 10.5, "middle", col, 700)
    return _svg(w, h, o)


def dotplot(rows: Sequence[Tuple[str, float, int]], lo: float, hi: float, band: Tuple[float, float], *,
            ref: Optional[float] = 1.0, ticks=(), w=640, label_w=130,
            fmtv: Callable = lambda v: f"DI {v:.2f}") -> str:
    if not rows:
        return ""
    pw = w - label_w - 90
    rh = 22
    h = len(rows) * rh + 30
    X = lambda v: label_w + pw * (min(max(v, lo), hi) - lo) / (hi - lo)
    o = f'<rect x="{X(band[0]):.1f}" y="0" width="{X(band[1]) - X(band[0]):.1f}" height="{h - 22}" fill="{C["band"]}"/>'
    for b in band:
        o += f'<line x1="{X(b):.1f}" x2="{X(b):.1f}" y1="0" y2="{h - 22}" stroke="{C["ok"]}" stroke-dasharray="3 2"/>'
    if ref is not None:
        o += f'<line x1="{X(ref):.1f}" x2="{X(ref):.1f}" y1="0" y2="{h - 22}" stroke="{C["mut"]}"/>'
    for tk in ticks:
        on = tk in band
        o += _t(X(tk), h - 8, f"{tk:g}", 9.5, "middle", C["ok"] if on else C["mut"], 600 if on else 400)
    for i, (k, v, n) in enumerate(rows):
        y = i * rh + 13
        out = v < band[0] or v > band[1]
        col = C["high"] if out else C["ok"]
        o += _t(label_w - 8, y + 4, k, 11, "end")
        o += f'<line x1="{X(ref if ref is not None else lo):.1f}" x2="{X(v):.1f}" y1="{y}" y2="{y}" stroke="{col}" stroke-width="2"/>'
        if out:
            o += (f'<path d="M{X(v) - 5:.1f},{y - 5} L{X(v) + 5:.1f},{y + 5} M{X(v) - 5:.1f},{y + 5} '
                  f'L{X(v) + 5:.1f},{y - 5}" stroke="{col}" stroke-width="2.6"/>')
        else:
            o += f'<circle cx="{X(v):.1f}" cy="{y}" r="5" fill="{col}"/>'
        o += _t(w - 2, y + 4, f"{fmtv(v)}  (n={n})", 10, "end", col, 600)
    return _svg(w, h, o)


# --------------------------------------------------------------------------- heatmap
def corr_heatmap(cols: List[str], M: Dict[str, Dict[str, float]], *, w=360) -> str:
    if not cols:
        return ""
    n = len(cols)
    lw = 118
    cs = (w - lw) / n

    def short(c: str, n: int = 11) -> str:
        return c if len(c) <= n else c[:n - 1] + "…"

    def colr(v):
        a = min(abs(v or 0), 1)
        if (v or 0) >= 0:
            r, g, b = (int(255 - (255 - 0x21) * a), int(255 - (255 - 0x66) * a), int(255 - (255 - 0xAC) * a))
        else:
            r, g, b = (int(255 - (255 - 0xB3) * a), int(255 - (255 - 0x58) * a), int(255 - (255 - 0x06) * a))
        return f"rgb({r},{g},{b})", ("#fff" if a > 0.55 else C["ink"])

    o = ""
    for j, c in enumerate(cols):
        o += _t(lw + j * cs + cs / 2, 12, short(c, max(4, int(cs / 5.6))), 8.5, "middle", C["mut"])
    for i, r in enumerate(cols):
        o += _t(lw - 6, 20 + i * cs + cs / 2 + 4, short(r), 9.5, "end")
        for j, c in enumerate(cols):
            v = (M.get(r) or {}).get(c)
            if v is None:
                continue
            bg, fg = colr(v)
            o += (f'<rect x="{lw + j * cs:.1f}" y="{20 + i * cs:.1f}" width="{cs - 2:.1f}" height="{cs - 2:.1f}" '
                  f'rx="3" fill="{bg}" stroke="#E3E6EA"/>')
            o += _t(lw + j * cs + cs / 2 - 1, 20 + i * cs + cs / 2 + 3, f"{v:.2f}", 9 if n > 6 else 9.5, "middle", fg, 600)
    return _svg(w, 20 + n * cs + 4, o)


def donut(part: int, total: int, *, size=120) -> str:
    r = 44
    frac = part / total if total else 0
    o = (f'<circle cx="60" cy="60" r="{r}" fill="none" stroke="{C["grid"]}" stroke-width="18"/>'
         f'<circle cx="60" cy="60" r="{r}" fill="none" stroke="{C["info"]}" stroke-width="18" '
         f'stroke-dasharray="{2 * math.pi * r * frac:.1f} 999" transform="rotate(-90 60 60)"/>')
    o += _t(60, 58, f"{part:,}", 18, "middle", w=700) + _t(60, 74, f"of {total:,}", 10, "middle", C["mut"])
    return _svg(size, size, o)


def dumbbell(rows: Sequence[Tuple[str, float, float]], *, lo=-0.5, hi=None, w=640, lw=150) -> str:
    """before (orange) -> after (green) per row; shaded |x|<0.5, dashed at 1."""
    if not rows:
        return ""
    hi = hi or max(4.0, math.ceil(max(max(abs(a), abs(b)) for _, a, b in rows)))
    lo = min(lo, math.floor(min(min(a, b) for _, a, b in rows)))
    pw = w - lw - 40
    X = lambda v: lw + pw * (v - lo) / (hi - lo)
    H = len(rows) * 30 + 9
    o = f'<rect x="{X(-0.5):.1f}" y="0" width="{X(0.5) - X(-0.5):.1f}" height="{H}" fill="{C["band"]}"/>'
    o += f'<line x1="{X(1):.1f}" x2="{X(1):.1f}" y1="0" y2="{H}" stroke="{C["warn"]}" stroke-dasharray="3 3"/>'
    for i, (k, a, b) in enumerate(rows):
        y = i * 30 + 24
        o += _t(lw - 8, y + 4, k, 11, "end")
        o += f'<line x1="{X(b):.1f}" x2="{X(a):.1f}" y1="{y}" y2="{y}" stroke="{C["mut"]}" stroke-width="2"/>'
        o += f'<circle cx="{X(a):.1f}" cy="{y}" r="6" fill="{C["warn"]}"/><circle cx="{X(b):.1f}" cy="{y}" r="6" fill="{C["ok"]}"/>'
        o += _t(X(a) + 10, y + 4, f"{a:.3f}", 10, w=600)
        o += _t(X(b), y - 9, f"{b:+.3f}", 9.5, "middle", C["ok"], 600)
    for tk in range(int(math.ceil(lo)), int(hi) + 1):
        o += _t(X(tk), H + 14, str(tk), 9.5, "middle", C["mut"])
    o += _t(X(0), H + 28, "0 = symmetric · shaded = |skew| < 0.5 · dashed = 1", 9.5, col=C["mut"])
    return _svg(w, H + 34, o)


# --------------------------------------------------------------------------- model bias (Aequitas)
_STATUS_COL = {"high": C["high"], "medium": C["warn"], "notice": C["info"], "ok": C["ok"], "small": C["na"], "ref": C["mut"]}


def disparity_bars(rows: Sequence[Tuple[str, Optional[float], str, str]], band: Tuple[float, float], *,
                   lo: float = 0.125, hi: float = 8.0, w=640, label_w=130, value_w=120) -> str:
    """Ratio vs reference group on a log2 axis centred on parity (1).

    rows = (group label, disparity or None, status key, right-hand note). Bars start at 1.
    Values outside [lo, hi] are clipped and drawn with an arrow; 0 is drawn as "0" at the left edge.
    """
    if not rows:
        return ""
    pw = w - label_w - value_w
    rh = 19
    h = len(rows) * rh + 30
    L = math.log2

    def X(v: float) -> float:
        v = min(max(v, lo), hi)
        return label_w + pw * (L(v) - L(lo)) / (L(hi) - L(lo))

    o = f'<rect x="{X(band[0]):.1f}" y="0" width="{X(band[1]) - X(band[0]):.1f}" height="{h - 22}" fill="{C["band"]}"/>'
    for b in band:
        o += f'<line x1="{X(b):.1f}" x2="{X(b):.1f}" y1="0" y2="{h - 22}" stroke="{C["ok"]}" stroke-dasharray="3 2"/>'
    o += f'<line x1="{X(1):.1f}" x2="{X(1):.1f}" y1="0" y2="{h - 22}" stroke="{C["ink"]}" stroke-width="1.2"/>'
    for tk in (lo, 0.25, 0.5, band[0], 1, band[1], 2, 4, hi):
        if lo <= tk <= hi:
            on = tk in band or tk == 1
            o += _t(X(tk), h - 8, f"{tk:g}" if tk >= 0.25 else f"≤{tk:g}" if tk == lo else f"{tk:g}", 9,
                    "middle", C["ok"] if tk in band else (C["ink"] if tk == 1 else C["mut"]), 600 if on else 400)
    for i, (k, v, st, note) in enumerate(rows):
        y = i * rh + 6
        col = _STATUS_COL.get(st, C["c1"])
        o += _t(label_w - 8, y + 12, k, 10.5, "end", C["mut"] if st == "small" else None, 700 if st == "ref" else 400)
        if v is None:
            o += _t(X(1) + 6, y + 12, "not available", 9.5, col=C["mut"])
        else:
            x0, x1 = sorted((X(1), X(v)))
            if st == "ref":
                o += f'<circle cx="{X(1):.1f}" cy="{y + 8}" r="4" fill="{C["ink"]}"/>'
            else:
                op = "0.55" if st == "small" else "1"
                o += f'<rect x="{x0:.1f}" y="{y + 2}" width="{max(x1 - x0, 2):.1f}" height="12" rx="2" fill="{col}" opacity="{op}"/>'
                if v > hi or v < lo:
                    ax = X(v)
                    d = 6 if v > hi else -6
                    o += f'<path d="M{ax:.1f},{y + 2} L{ax + d:.1f},{y + 8} L{ax:.1f},{y + 14} Z" fill="{col}"/>'
        o += _t(w - 2, y + 12, note, 9.5, "end", col if st not in ("ref", "ok") else C["mut"], 600 if st in ("high", "notice") else 400)
    return _svg(w, h, o)


def rate_shift(rows: Sequence[Tuple[str, Optional[float], Optional[float], Optional[int], bool, bool]], *,
               w=640, label_w=130, value_w=150) -> str:
    """Actual positive rate (hollow) -> predicted positive rate (filled) per group, 0-100 %.

    rows = (group, actual rate, predicted rate, n, is_reference, is_small).
    """
    if not rows:
        return ""
    pw = w - label_w - value_w
    rh = 22
    h = len(rows) * rh + 44
    X = lambda v: label_w + pw * v
    o = ""
    for tk in (0, 0.25, 0.5, 0.75, 1):
        o += f'<line x1="{X(tk):.1f}" x2="{X(tk):.1f}" y1="0" y2="{h - 36}" stroke="{C["grid"]}"/>'
        o += _t(X(tk), h - 24, f"{int(tk * 100)}%", 9, "middle", C["mut"])
    for i, (k, a, p, n, ref, small) in enumerate(rows):
        y = i * rh + 10
        op = "0.5" if small else "1"
        o += _t(label_w - 8, y + 4, k + (" (ref.)" if ref else ""), 10.5, "end", C["mut"] if small else None, 700 if ref else 400)
        if a is not None and p is not None:
            o += f'<g opacity="{op}"><line x1="{X(a):.1f}" x2="{X(p):.1f}" y1="{y}" y2="{y}" stroke="{C["c1"]}" stroke-width="2.5"/>'
            o += f'<circle cx="{X(a):.1f}" cy="{y}" r="5" fill="#fff" stroke="{C["c1"]}" stroke-width="2"/>'
            o += f'<circle cx="{X(p):.1f}" cy="{y}" r="5" fill="{C["c1"]}"/></g>'
            diff = (p - a) * 100
            o += _t(w - 2, y + 4, f"{pct(a, 0)} → {pct(p, 0)} ({diff:+.0f} pts)" + (f" · n={n}" if n is not None else ""),
                    9.5, "end", C["mut"], 400)
    o += f'<circle cx="{label_w + 5}" cy="{h - 6}" r="4" fill="#fff" stroke="{C["c1"]}" stroke-width="2"/>' + _t(label_w + 13, h - 2, "actual positive rate (test labels)", 9, col=C["mut"])
    o += f'<circle cx="{label_w + 205}" cy="{h - 6}" r="4" fill="{C["c1"]}"/>' + _t(label_w + 213, h - 2, "predicted positive rate (selection rate)", 9, col=C["mut"])
    return _svg(w, h, o)


def confusion(tp: int, fp: int, fn: int, tn: int, *, w=300) -> str:
    """2x2 confusion matrix; correct cells green-tinted, error cells orange-tinted."""
    cs = 92
    x0, y0 = 110, 34
    cells = [((0, 0), tp, "True positive", "#DFF3EC", C["ok"]), ((1, 0), fn, "False negative", "#FBE7DC", C["high"]),
             ((0, 1), fp, "False positive", "#FBE7DC", C["high"]), ((1, 1), tn, "True negative", "#DFF3EC", C["ok"])]
    o = _t(x0 + cs, 12, "Model predicted", 9.5, "middle", C["mut"], 600)
    o += _t(x0 + cs / 2, 28, "positive (1)", 9, "middle", C["mut"]) + _t(x0 + cs * 1.5, 28, "negative (0)", 9, "middle", C["mut"])
    o += _t(x0 - 8, y0 + cs / 2 + 4, "actual 1", 9.5, "end", C["mut"]) + _t(x0 - 8, y0 + cs * 1.5 + 4, "actual 0", 9.5, "end", C["mut"])
    for (cx, cy), v, lab, bg, col in cells:
        x, y = x0 + cx * cs, y0 + cy * cs
        o += f'<rect x="{x}" y="{y}" width="{cs - 3}" height="{cs - 3}" rx="6" fill="{bg}" stroke="{col}"/>'
        o += _t(x + cs / 2 - 1, y + cs / 2, f"{v:,}", 20, "middle", col, 800)
        o += _t(x + cs / 2 - 1, y + cs / 2 + 18, lab, 8.5, "middle", C["mut"])
    return _svg(w, y0 + 2 * cs + 4, o)
