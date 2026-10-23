"""Header: the name arrives as a deep-space downlink and is decoded out of the noise."""
from __future__ import annotations

import math
import random

from svgterm import THEMES, Clock, Grid, animate_rows, num, svg_doc, text_el

COLS = 88
FS, CW = 15, 9.0
PAD_X = 24
WIDTH = 2 * PAD_X + COLS * CW
BAR_H = 34

# ANSI Shadow, the classic figlet font
LETTERS = {
    "R": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
    "A": [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    "M": ["███╗   ███╗", "████╗ ████║", "██╔████╔██║", "██║╚██╔╝██║", "██║ ╚═╝ ██║",
          "╚═╝     ╚═╝"],
    "O": [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "N": ["███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║",
          "╚═╝  ╚═══╝"],
}
BIG = ["".join(LETTERS[c][i] for c in "RAMON") for i in range(6)]
BIG_COL, INFO_COL = 2, 54

COMMAND = "$ ./downlink --band X --target ramon"
NOISE = "░▒▓·:;=+*#%&@$?!/\\|<>~^01"

# content rows: 0 command, 1 lock status, 3-8 name, 10 link meter
ROW_H = [20, 20, 14, 16, 16, 16, 16, 16, 16, 16, 20]
PAYLOAD = range(3, 9)

DT = 60
T_TYPED = 1100
T_CARRIER = 1800
LOCKS = [("CARRIER", T_CARRIER), ("SYMBOL", 2500), ("FRAME", 3300), ("FEC", 4000)]
T_DEC0, T_DEC1 = 2100, 4100
T_END = 4500
EBN0 = 12.4
LOOP = 9000          # after the decode: steady link with a short glitch
GLITCH_AT, GLITCH_FRAMES = 6200, 4


def _final() -> Grid:
    g = Grid(COLS, len(ROW_H))
    for i, line in enumerate(BIG):
        for j, c in enumerate(line):
            g.put(3 + i, BIG_COL + j, c, "G" if c == "█" else "d")
    info = [
        [("// hi, i'm ", "d"), ("ramon", "b")],
        [],
        [("telecommunications engineering", None)],
        [("student", None), (" · ", "d"), ("ML enthusiast", None)],
        [("antennas", None), (" · ", "d"), ("RF", None), (" · ", "d"), ("open source", None)],
        [("now ", "a"), ("→ ", "d"), ("deep space telecom", None)],
    ]
    for i, parts in enumerate(info):
        col = INFO_COL
        for text, cls in parts:
            g.put(3 + i, col, text, cls)
            col += len(text)
    return g


def _ber(ebn0_db: float) -> float:
    """BPSK/QPSK bit error rate over AWGN."""
    return 0.5 * math.erfc(math.sqrt(10 ** (ebn0_db / 10)))


def _status(g: Grid, t: int, rnd: random.Random, glitch: bool = False):
    col = 2
    for name, t_lock in LOCKS:
        if t >= t_lock and not (glitch and name == "FEC"):
            dot, dcls, lcls = "●", "g", None
        elif t >= t_lock - 700 or glitch:
            dot, dcls, lcls = ("●" if (t // DT) % 2 else "○"), "a", "d"
        else:
            dot, dcls, lcls = "○", "n", "n"
        g.put(1, col, dot, dcls)
        g.put(1, col + 2, name, lcls)
        col += len(name) + 5
    if t < T_CARRIER:
        g.put(1, 60, "searching carrier " + "|/-\\"[(t // DT) % 4], "d")
    else:
        df = -2.31 * math.exp(-(t - T_CARRIER) / 450) + rnd.uniform(-0.02, 0.02)
        g.put(1, 60, f"Δf {df:+.2f} kHz", "d")
        g.put(1, 76, f"{_snr(t, glitch) + 37.5:4.1f} dB-Hz", "d")


def _snr(t: int, glitch: bool = False) -> float:
    if t < T_CARRIER:
        return 0.0
    x = min(1.0, (t - T_CARRIER) / (LOCKS[-1][1] - T_CARRIER))
    snr = EBN0 * (1 - (1 - x) ** 2.2)
    return snr - (2.7 if glitch else 0)


def _meter(g: Grid, t: int, rnd: random.Random, glitch: bool = False):
    snr = _snr(t, glitch)
    jitter = rnd.uniform(-0.15, 0.15) if t >= T_CARRIER else 0
    g.put(10, 2, "Eb/N0", "d")
    bars = 24
    filled = round(min(1, (snr + jitter) / 16) * bars) if t >= T_CARRIER else 0
    good = "g" if snr > 9 else "a"
    g.put(10, 8, "█" * filled, good)
    g.put(10, 8 + filled, "░" * (bars - filled), "n")
    if t >= T_CARRIER:
        g.put(10, 34, f"{max(0.0, snr + jitter):4.1f} dB", None)
        g.put(10, 44, "BER", "d")
        g.put(10, 48, f"{_ber(max(0.0, snr + jitter)):.1e}", None)
    else:
        g.put(10, 34, " --.- dB", "d")
        g.put(10, 44, "BER  -------", "d")
    locked = t >= T_END and not glitch
    g.put(10, 74, "● LOCKED" if locked else ("○ ACQUIRING" if t >= T_CARRIER else "○ NO SIGNAL"),
          "g" if locked else ("a" if t >= T_CARRIER else "n"))


def _noise(rnd: random.Random) -> tuple[str, str]:
    return rnd.choice(NOISE), ("d" if rnd.random() < 0.3 else "n")


def _decode_frames(final: Grid, rnd: random.Random) -> tuple[list[Grid], list[int]]:
    lock = [[T_DEC0 + (T_DEC1 - T_DEC0) * (0.55 * rnd.random() + 0.45 * c / COLS)
             for c in range(COLS)] for _ in range(len(ROW_H))]
    frames = []
    for t in range(0, T_END + DT, DT):
        g = Grid(COLS, len(ROW_H))
        typed = COMMAND[:max(0, t // 30)]
        g.put(0, 2, typed[:1], "g")
        g.put(0, 3, typed[1:])
        if t < T_CARRIER and (t // 240) % 2 == 0:
            g.put(0, 2 + len(typed), "█", "d")
        if t >= T_TYPED:
            _status(g, t, rnd)
        _meter(g, t, rnd)
        progress = min(1.0, max(0.0, (t - T_CARRIER) / (T_DEC1 - T_CARRIER)))
        for r in PAYLOAD:
            for c in range(1, COLS - 1):
                ch, cls = final.ch[r][c], final.cl[r][c]
                if t < T_TYPED:
                    continue
                if t < T_CARRIER:
                    if rnd.random() < 0.05:
                        g.put(r, c, *_noise(rnd))
                elif ch != " ":
                    if t >= lock[r][c]:
                        if rnd.random() < 0.3 * math.exp(-(t - lock[r][c]) / 250):
                            g.put(r, c, *_noise(rnd))
                        else:
                            g.put(r, c, ch, cls)
                    elif rnd.random() < 0.6:
                        g.put(r, c, *_noise(rnd))
                elif rnd.random() < 0.3 * (1 - progress):
                    g.put(r, c, *_noise(rnd))
        frames.append(g)
    return frames, [DT] * len(frames)


def _steady(final: Grid, rnd: random.Random, glitch: bool) -> Grid:
    g = final.copy()
    g.put(0, 2, COMMAND[:1], "g")
    g.put(0, 3, COMMAND[1:])
    _status(g, T_END, rnd, glitch)
    _meter(g, T_END, rnd, glitch)
    if glitch:
        for r in rnd.sample(list(PAYLOAD), 2):
            shift = rnd.choice([-3, -2, 2, 3])
            ch, cl = g.ch[r][:], g.cl[r][:]
            for c in range(COLS):
                src = c - shift
                g.ch[r][c], g.cl[r][c] = (ch[src], cl[src]) if 0 <= src < COLS else (" ", None)
        for r in PAYLOAD:
            for c in range(1, COLS - 1):
                if rnd.random() < 0.06:
                    g.put(r, c, *_noise(rnd))
    return g


def _layer(frames: list[Grid], big: bool) -> list[Grid]:
    """Split the name block from the rest: it is drawn with a taller font so blocks touch."""
    out = []
    for g in frames:
        v = g.copy()
        for r in range(v.rows):
            for c in range(v.cols):
                if (r in PAYLOAD and c < INFO_COL - 2) != big:
                    v.ch[r][c], v.cl[r][c] = " ", None
        out.append(v)
    return out


def build(theme: str) -> str:
    rnd = random.Random(1977)          # Voyager launch year; same frames in both themes
    final = _final()
    clock = Clock()

    ys, y = [], BAR_H + 16
    for h in ROW_H:
        ys.append(y + h - 5)
        y += h
    height = y + 14

    once, once_d = _decode_frames(final, rnd)
    steady = [_steady(final, rnd, False)]
    loop_d = [GLITCH_AT]
    for _ in range(GLITCH_FRAMES):
        steady.append(_steady(final, rnd, True))
        loop_d.append(DT)
    steady.append(_steady(final, rnd, False))
    loop_d.append(LOOP - GLITCH_AT - GLITCH_FRAMES * DT)
    t_once = sum(once_d)

    body = [f'<rect x="1" y="1" width="{num(WIDTH - 2)}" height="{BAR_H}" rx="9" class="bar"/>',
            f'<rect x="1" y="{BAR_H - 8}" width="{num(WIDTH - 2)}" height="9" class="bar"/>',
            f'<line x1="1" x2="{num(WIDTH - 1)}" y1="{BAR_H + 1}" y2="{BAR_H + 1}" class="sep"/>',
            f'<text x="{PAD_X}" y="22" class="t live">●</text>',
            text_el(((" RX-01 · distortedsignal.com", "d"),), PAD_X + 10, 22, 7.2, ' class="t"'),
            text_el((("X-BAND · 8.420 GHz · QPSK r=1/2", "d"),), WIDTH - PAD_X - 31 * 7.2, 22,
                    7.2, ' class="t"')]
    for big in (False, True):
        cls = "big" if big else ""
        body += animate_rows(_layer(once, big), once_d, PAD_X, ys, CW, clock, cls=cls, hold=False)
        body += animate_rows(_layer(steady, big), loop_d, PAD_X, ys, CW, clock, cls=cls,
                             loop=True, start=t_once)
    cursor_x = PAD_X + (INFO_COL + len("// hi, i'm ramon")) * CW
    body.append(f'<g class="k" style="{clock.window(t_once)}">'
                f'<text x="{num(cursor_x)}" y="{num(ys[3])}" class="b blink">▌</text></g>')

    css = (f"text{{font-size:{FS}px}}.t{{font-size:12px}}.big{{font-size:19px}}.big .G{{stroke:url(#grad);stroke-width:.7}}"
           f"@keyframes blink{{50%{{opacity:0}}}}.blink{{animation:blink 1.1s step-end infinite}}"
           f"@keyframes live{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}"
           f".live{{animation:live 2.4s ease-in-out infinite}}"
           + clock.css())
    t = THEMES[theme]
    css += (f".bar{{fill:{t['bar']}}}.sep{{stroke:{t['border']}}}.live{{fill:{t['green']}}}")
    big_x0 = PAD_X + BIG_COL * CW
    return svg_doc(WIDTH, height, theme, body, css, title="Hi, I'm Ramon",
                   grad_box=(big_x0, ys[3] - 12, big_x0 + len(BIG[0]) * CW, ys[8]))
