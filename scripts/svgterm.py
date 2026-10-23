"""Character grids rendered as animated SVG.

GitHub shows README images through <img>, which never runs scripts, so every
animation here is plain CSS: pre-rendered frames whose opacity is switched on
and off by keyframes.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

FONT = ("ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,"
        "'Liberation Mono','DejaVu Sans Mono',monospace")

THEMES = {
    "dark": dict(bg="#0d1117", bar="#161b22", border="#30363d", fg="#c9d1d9",
                 dim="#7d8590", faint="#3d444d", blue="#58a6ff", green="#3fb950",
                 amber="#d29922", red="#f85149", grad=("#58a6ff", "#3fb950")),
    "light": dict(bg="#ffffff", bar="#f6f8fa", border="#d0d7de", fg="#1f2328",
                  dim="#656d76", faint="#c4ccd5", blue="#0969da", green="#1a7f37",
                  amber="#9a6700", red="#cf222e", grad=("#0969da", "#1a7f37")),
}

# tspan class -> theme colour
COLOURS = {"d": "dim", "n": "faint", "b": "blue", "g": "green", "a": "amber", "r": "red"}


def num(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


class Grid:
    """A rows x cols block of characters, each with an optional colour class."""

    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = cols, rows
        self.ch = [[" "] * cols for _ in range(rows)]
        self.cl = [[None] * cols for _ in range(rows)]

    def put(self, row: int, col: int, text: str, cls: str | None = None):
        if not 0 <= row < self.rows:
            return
        for i, c in enumerate(text):
            if 0 <= col + i < self.cols:
                self.ch[row][col + i] = c
                self.cl[row][col + i] = cls

    def copy(self) -> "Grid":
        g = Grid(self.cols, self.rows)
        g.ch = [r[:] for r in self.ch]
        g.cl = [r[:] for r in self.cl]
        return g

    def runs(self, row: int) -> tuple:
        """The row as hashable (text, cls) runs; spaces join the previous run."""
        out: list[list] = []
        for c, k in zip(self.ch[row], self.cl[row]):
            if c == " " and out:
                k = out[-1][1]
            if out and out[-1][1] == k:
                out[-1][0] += c
            else:
                out.append([c, k])
        return tuple((t, k) for t, k in out)


def text_el(runs: tuple, x: float, y: float, cw: float, attrs: str = "") -> str:
    """One <text> line, trimmed; textLength squeezes any font onto the grid, gap-free."""
    s = "".join(t for t, _ in runs)
    body = s.strip(" ")
    if not body:
        return ""
    start = len(s) - len(s.lstrip(" "))
    end = start + len(body)
    parts, pos = [], 0
    for t, k in runs:
        a, b = max(pos, start), min(pos + len(t), end)
        if a < b:
            seg = escape(t[a - pos:b - pos])
            parts.append(f'<tspan class="{k}">{seg}</tspan>' if k else seg)
        pos += len(t)
    return (f'<text x="{num(x + start * cw)}" y="{num(y)}" '
            f'textLength="{num(len(body) * cw)}" lengthAdjust="spacingAndGlyphs"{attrs}>'
            f'{"".join(parts)}</text>')


class Clock:
    """Builds the CSS that shows an element only during given time windows."""

    def __init__(self):
        self._kf = {"on": "@keyframes on{from,to{opacity:1}}"}

    def window(self, t0: int, t1: int | None = None) -> str:
        """Visible once during [t0, t1); with no t1 it stays visible."""
        if t1 is None:
            return f"animation:on 1ms {t0}ms forwards"
        return f"animation:on {t1 - t0}ms {t0}ms"

    def cycle(self, t0: int, t1: int, period: int, start: int = 0) -> str:
        """Visible during [t0, t1) of every period, the first one beginning at start."""
        if t1 - t0 >= period:
            return self.window(start)
        pct = f"{(t1 - t0) * 100 / period:.3f}".rstrip("0").rstrip(".")
        name = "c" + pct.replace(".", "_")
        self._kf[name] = f"@keyframes {name}{{0%{{opacity:1}}{pct}%,to{{opacity:0}}}}"
        return f"animation:{name} {period}ms step-end {start + t0}ms infinite"

    def css(self) -> str:
        return "".join(self._kf.values())


def _attrs(cls: str, style: str) -> str:
    return f' class="{(cls + " k").strip()}" style="{style}"'


def animate_rows(frames: list[Grid], durations: list[int], x: float, ys: list[float],
                 cw: float, clock: Clock, *, cls: str = "", loop: bool = False,
                 start: int = 0, hold: bool = True) -> list[str]:
    """Per-row animation: a row only gets a new element when its content changes.

    Suits mostly static grids (the header). Without `loop` the frames play once
    from `start`, and with `hold` the last state stays on screen afterwards.
    """
    total = sum(durations)
    out = []
    for r in range(frames[0].rows):
        spans: list[list] = []
        t = 0
        for g, d in zip(frames, durations):
            runs = g.runs(r)
            if spans and spans[-1][0] == runs:
                spans[-1][2] = t + d
            else:
                spans.append([runs, t, t + d])
            t += d
        for runs, t0, t1 in spans:
            if loop:
                style = clock.cycle(t0, t1, total, start)
            elif hold and t1 == total:
                style = clock.window(start + t0) if (start + t0) else ""
            else:
                style = clock.window(start + t0, start + t1)
            el = text_el(runs, x, ys[r], cw, _attrs(cls, style) if style else
                         (f' class="{cls}"' if cls else ""))
            if el:
                out.append(el)
    return out


def animate_frames(frames: list[Grid], dt: int, x: float, ys: list[float], cw: float,
                   clock: Clock, *, cls: str = "") -> list[str]:
    """Whole-frame looping animation; suits grids where everything moves (the dish)."""
    period = dt * len(frames)
    out = []
    for i, g in enumerate(frames):
        rows = [text_el(g.runs(r), x, ys[r], cw) for r in range(g.rows)]
        out.append(f'<g{_attrs(cls, clock.cycle(i * dt, (i + 1) * dt, period))}>'
                   + "".join(e for e in rows if e) + "</g>")
    return out


def svg_doc(width: float, height: float, theme: str, body: list[str], css: str,
            defs: str = "", title: str = "", grad_box: tuple | None = None) -> str:
    """Wraps body elements in a themed card. Class G fills with a gradient over grad_box."""
    t = THEMES[theme]
    colours = "".join(f".{k}{{fill:{t[v]}}}" for k, v in COLOURS.items())
    style = (f"text{{font-family:{FONT};white-space:pre;fill:{t['fg']}}}"
             f".k{{opacity:0}}{colours}.G{{fill:url(#grad)}}{css}")
    g0, g1 = t["grad"]
    x1, y1, x2, y2 = grad_box or (0, 0, width, height)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{num(width)}" '
            f'height="{num(height)}" viewBox="0 0 {num(width)} {num(height)}" '
            f'xml:space="preserve" role="img"><title>{escape(title)}</title>'
            f'<defs><linearGradient id="grad" gradientUnits="userSpaceOnUse" '
            f'x1="{num(x1)}" y1="{num(y1)}" x2="{num(x2)}" y2="{num(y2)}">'
            f'<stop offset="0" stop-color="{g0}"/><stop offset="1" stop-color="{g1}"/>'
            f'</linearGradient>{defs}</defs><style>{style}</style>'
            f'<rect x="0.5" y="0.5" width="{num(width - 1)}" height="{num(height - 1)}" '
            f'rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>'
            + "".join(body) + "</svg>")
