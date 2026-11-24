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
