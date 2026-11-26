"""Static SVG line charts for the research notes. No dependencies.

The figures follow one set of rules so they read as one system: a single
y-axis; 2px lines; a legend for two or more series and a direct label at each
line's end; text in text inks, never in the series colour; a solid hairline
grid; colours taken from a palette that was checked for colour-blind
separation and contrast in both light and dark, each mode with its own steps.
A figure is a static image, so the table beside it in the note carries every
value.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

PALETTES = {
    # identity: which series. Fixed order, never cycled.
    "categorical": {"light": ["#257de0", "#f47230", "#00b894"], "dark": ["#338ced", "#e76624", "#00a888"]},
    # position in a sequence: one hue, weaker to stronger. The ramp flips on a dark surface.
    "ordinal": {"light": ["#84b9f3", "#257de0", "#0f4a96"], "dark": ["#1757ac", "#338ced", "#9dc8f7"]},
}
CHROME = {
    "light": {"surface": "#ffffff", "ink": "#191919", "ink2": "#666666", "grid": "#e7e7e7", "axis": "#c2c2c2"},
    "dark": {"surface": "#191919", "ink": "#efefef", "ink2": "#9c9c9c", "grid": "#303030", "axis": "#474747"},
}
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def nice_ticks(low: float, high: float, target: int = 5) -> List[float]:
    if not (high > low):
        return [low]
    raw = (high - low) / max(target, 1)
    magnitude = 10.0 ** math.floor(math.log10(raw))
    step = magnitude
    for multiple in (1.0, 2.0, 2.5, 5.0, 10.0):
        step = multiple * magnitude
        if (high - low) / step <= target + 0.5:
            break
    first = math.ceil(low / step - 1e-9) * step
    ticks = []
    value = first
    while value <= high + step * 1e-9:
        ticks.append(0.0 if abs(value) < step * 1e-9 else round(value, 12))
        value += step
    return ticks


def log_ticks(low: float, high: float) -> List[float]:
    lo, hi = math.floor(math.log10(low)), math.ceil(math.log10(high))
    multiples = (1.0,) if hi - lo >= 3 else (1.0, 2.0, 5.0)
    return [m * 10.0 ** e for e in range(lo, hi + 1) for m in multiples if low * 0.999 <= m * 10.0 ** e <= high * 1.001]


def _esc(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _compact(value: float) -> str:
    if value == 0:
        return "0"
    magnitude = abs(value)
    if magnitude >= 1e6:
        return "{0:g}M".format(round(value / 1e6, 2))
    if magnitude >= 1e4:
        return "{0:g}K".format(round(value / 1e3, 2))
    if magnitude >= 100:
        return "{0:,.0f}".format(value)
    return "{0:g}".format(round(value, 4))


def line_chart(series: Sequence[Dict[str, Any]], title: str, subtitle: str = "", x_label: str = "", y_label: str = "",
               width: int = 760, height: int = 400, log_y: bool = False, palette: str = "categorical",
               y_format: Optional[Callable[[float], str]] = None, x_format: Optional[Callable[[float], str]] = None,
               h_lines: Sequence[Tuple[float, str]] = (), v_lines: Sequence[Tuple[float, str]] = (),
               y_range: Optional[Tuple[float, float]] = None, x_ticks: Optional[Sequence[float]] = None,
               markers: bool = False, description: str = "") -> str:
    """One chart. `series` is a list of {"name", "x", "y"}; at most three, in a fixed order."""
    if not series or len(series) > 3:
        raise ValueError("one to three series; fold the rest or facet into small multiples")
    y_format = y_format or _compact
    x_format = x_format or (lambda v: "{0:g}".format(v))
    points = [[(float(a), float(b)) for a, b in zip(s["x"], s["y"]) if math.isfinite(float(a)) and math.isfinite(float(b))
               and (not log_y or float(b) > 0)] for s in series]
    xs = [p[0] for pts in points for p in pts]
    ys = [p[1] for pts in points for p in pts] + [v for v, _ in h_lines]
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = (min(ys), max(ys)) if y_range is None else y_range
    if log_y:
        ticks_y = log_ticks(y_lo, y_hi)
        y_lo, y_hi = min([y_lo] + ticks_y), max([y_hi] + ticks_y)
    else:
        ticks_y = nice_ticks(y_lo, y_hi)
        if y_range is None:
            step = ticks_y[1] - ticks_y[0] if len(ticks_y) > 1 else 1.0
            y_lo = min(y_lo, ticks_y[0])
            y_hi = max(y_hi, ticks_y[-1])
            if y_hi - ticks_y[-1] > 1e-9:
                ticks_y.append(round(ticks_y[-1] + step, 12))
                y_hi = ticks_y[-1]
            if ticks_y[0] - y_lo > 1e-9:
                ticks_y.insert(0, round(ticks_y[0] - step, 12))
                y_lo = ticks_y[0]
    ticks_x = list(x_ticks) if x_ticks is not None else nice_ticks(x_lo, x_hi, 6)
    ticks_x = [t for t in ticks_x if x_lo - 1e-9 <= t <= x_hi + 1e-9]

    left, right, bottom = 58, 132, 46
    top = (96 if len(series) > 1 else 72) if y_label else (78 if len(series) > 1 else 58)
    plot_w, plot_h = width - left - right, height - top - bottom

    def sx(value: float) -> float:
        return left + (value - x_lo) / (x_hi - x_lo or 1.0) * plot_w

    def sy(value: float) -> float:
        if log_y:
            return top + plot_h - (math.log10(value) - math.log10(y_lo)) / (math.log10(y_hi) - math.log10(y_lo) or 1.0) * plot_h
        return top + plot_h - (value - y_lo) / (y_hi - y_lo or 1.0) * plot_h

    colours = PALETTES[palette]
    css = ["svg{font-family:" + FONT + "}"]
    for mode in ("light", "dark"):
        rules = "".join("--{0}:{1};".format(key, value) for key, value in CHROME[mode].items())
        rules += "".join("--s{0}:{1};".format(i + 1, colour) for i, colour in enumerate(colours[mode]))
        css.append("svg{" + rules + "}" if mode == "light" else "@media (prefers-color-scheme: dark){svg{" + rules + "}}")
    css += [
        ".bg{fill:var(--surface)}", ".t{fill:var(--ink);font-size:15px;font-weight:600}",
        ".st{fill:var(--ink2);font-size:12px}", ".tk{fill:var(--ink2);font-size:11px;font-variant-numeric:tabular-nums}",
        ".lb{fill:var(--ink);font-size:12px}",
        ".lb2{fill:var(--ink2);font-size:11px;paint-order:stroke;stroke:var(--surface);stroke-width:4px;stroke-linejoin:round}",
        ".g{stroke:var(--grid);stroke-width:1}", ".ax{stroke:var(--axis);stroke-width:1}", ".ld{stroke:var(--ink2);stroke-width:1}",
        ".ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}", ".dot{stroke:var(--surface);stroke-width:2}",
    ]
    css += [".c{0}{{stroke:var(--s{0})}}.f{0}{{fill:var(--s{0})}}".format(i + 1) for i in range(len(series))]

    out: List[str] = []
    add = out.append
    label = description or "{0}. {1}".format(title, subtitle)
    add('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {0} {1}" width="{0}" height="{1}" role="img" aria-label="{2}">'.format(width, height, _esc(label)))
    add("<title>{0}</title><style>{1}</style>".format(_esc(title), "".join(css)))
    add('<rect class="bg" width="{0}" height="{1}"/>'.format(width, height))
    add('<text class="t" x="{0}" y="24">{1}</text>'.format(left, _esc(title)))
    if subtitle:
        add('<text class="st" x="{0}" y="42">{1}</text>'.format(left, _esc(subtitle)))
    if len(series) > 1:
        x = left
        for i, s in enumerate(series):
            add('<line class="ln c{0}" x1="{1}" y1="60" x2="{2}" y2="60"/>'.format(i + 1, x, x + 16))
            add('<text class="st" x="{0}" y="64">{1}</text>'.format(x + 22, _esc(s["name"])))
            x += 22 + 7 * len(str(s["name"])) + 18
    for tick in ticks_y:
        y = sy(tick)
        add('<line class="g" x1="{0}" y1="{1:.1f}" x2="{2}" y2="{1:.1f}"/>'.format(left, y, left + plot_w))
        add('<text class="tk" x="{0}" y="{1:.1f}" text-anchor="end">{2}</text>'.format(left - 8, y + 4, _esc(y_format(tick))))
    add('<line class="ax" x1="{0}" y1="{1}" x2="{2}" y2="{1}"/>'.format(left, top + plot_h, left + plot_w))
    for tick in ticks_x:
        x = sx(tick)
        add('<line class="ax" x1="{0:.1f}" y1="{1}" x2="{0:.1f}" y2="{2}"/>'.format(x, top + plot_h, top + plot_h + 4))
        add('<text class="tk" x="{0:.1f}" y="{1}" text-anchor="middle">{2}</text>'.format(x, top + plot_h + 18, _esc(x_format(tick))))
    if x_label:
        add('<text class="st" x="{0:.1f}" y="{1}" text-anchor="middle">{2}</text>'.format(left + plot_w / 2, height - 8, _esc(x_label)))
    if y_label:
        add('<text class="st" x="{0}" y="{1}">{2}</text>'.format(left - 46, top - 12, _esc(y_label)))
    for value, text in h_lines:
        y = sy(value)
        add('<line class="ax" x1="{0}" y1="{1:.1f}" x2="{2}" y2="{1:.1f}"/>'.format(left, y, left + plot_w))
        add('<text class="lb2" x="{0}" y="{1:.1f}">{2}</text>'.format(left + 6, y - 5, _esc(text)))
    for value, text in v_lines:
        x = sx(value)
        add('<line class="ax" x1="{0:.1f}" y1="{1}" x2="{0:.1f}" y2="{2}"/>'.format(x, top, top + plot_h))
        add('<text class="lb2" x="{0:.1f}" y="{1}">{2}</text>'.format(x + 6, top + 12, _esc(text)))
    ends = []
    for i, pts in enumerate(points):
        if not pts:
            continue
        path = " ".join("{0}{1:.1f},{2:.1f}".format("M" if j == 0 else "L", sx(a), sy(b)) for j, (a, b) in enumerate(pts))
        add('<path class="ln c{0}" d="{1}"/>'.format(i + 1, path))
        if markers:
            for a, b in pts[:-1]:
                add('<circle class="dot f{0}" cx="{1:.1f}" cy="{2:.1f}" r="4"/>'.format(i + 1, sx(a), sy(b)))
        add('<circle class="dot f{0}" cx="{1:.1f}" cy="{2:.1f}" r="4"/>'.format(i + 1, sx(pts[-1][0]), sy(pts[-1][1])))
        ends.append([sy(pts[-1][1]), sx(pts[-1][0]), series[i].get("end_label", series[i]["name"])])
    # direct labels at the line ends; where they would collide, spread them and draw a leader
    order = sorted(range(len(ends)), key=lambda k: ends[k][0])
    placed = [ends[k][0] for k in order]
    for j in range(1, len(placed)):
        placed[j] = max(placed[j], placed[j - 1] + 15)
    overflow = placed[-1] - (top + plot_h) if placed else 0
    if overflow > 0:
        placed = [p - overflow for p in placed]
        for j in range(len(placed) - 2, -1, -1):
            placed[j] = min(placed[j], placed[j + 1] - 15)
    for j, k in enumerate(order):
        y0, x0, text = ends[k]
        if abs(placed[j] - y0) > 3:
            add('<line class="ld" x1="{0:.1f}" y1="{1:.1f}" x2="{2:.1f}" y2="{3:.1f}"/>'.format(x0 + 6, y0, x0 + 14, placed[j]))
        add('<text class="lb" x="{0:.1f}" y="{1:.1f}">{2}</text>'.format(x0 + 16, placed[j] + 4, _esc(text)))
    add("</svg>")
    return "".join(out) + "\n"
