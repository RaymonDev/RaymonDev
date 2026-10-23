"""Ground station card: a spinning ASCII dish next to live telemetry from DSN Madrid."""
from __future__ import annotations

import random

import numpy as np

import dish3d
from svgterm import THEMES, Clock, Grid, animate_frames, animate_rows, num, svg_doc, text_el

WIDTH = 840
DISH_X, DISH_Y = 18, 20
DISH_COLS, DISH_ROWS, DISH_CW, DISH_LH, DISH_FS = 70, 38, 6.0, 10.0, 10
DISH_FRAMES, DISH_DT = 72, 110
PANEL_X, PANEL_Y = 462, 24
PANEL_COLS, PANEL_ROWS, PANEL_CW, PANEL_LH, PANEL_FS = 46, 22, 7.8, 18, 13
SPEC_ROW, TICKER_ROW = 12, 15

ACTIVITY = {
    "Spacecraft Telemetry, Tracking, and Command": "tracking",
    "Antenna Calibration": "calibration",
    "Antenna Preventative Maintenance": "maintenance",
    "Engineering Upgrades": "upgrades",
}
ASM = ["1A", "CF", "FC", "1D"]      # CCSDS attached sync marker


def _rate(bps: float) -> str:
    if bps >= 1e6:
        return f"{bps / 1e6:.2f} Mb/s"
    if bps >= 1e3:
        return f"{bps / 1e3:.1f} kb/s"
    return f"{bps:.0f} b/s" if bps > 0 else "—"


def _rtlt(s: float) -> str:
    if s <= 0:
        return "—"
    if s < 60:
        return f"{s:.2f} s"
    h, rem = divmod(int(s), 3600)
    return f"{h}h {rem // 60:02d}m {rem % 60:02d}s" if h else f"{rem // 60}m {rem % 60:02d}s"


def _range(km: float) -> str:
    if km <= 0:
        return "—"
    if km >= 1.5e7:
        return f"{km / 1.496e8:.2f} AU"
    return f"{km / 1e6:.2f} Mkm" if km >= 1e6 else f"{km:,.0f} km"


def _dish_label(d: dict) -> tuple[str, str]:
    name = d["name"].replace("DSS", "DSS ")
    size = d["type"][:2] + " m" if d["type"][:2].isdigit() else ""
    return name, size


def _featured(dishes: list[dict]) -> dict | None:
    def score(d):
        rtlt = max([t["rtlt"] for t in d["targets"]] or [-1])
        return bool(d["down"]), bool(d["targets"]), rtlt, d["type"].startswith("70")
    best = max(dishes, key=score, default=None)
    return best if best and best["targets"] else None


def _panel(snap: dict | None) -> tuple[Grid, dict | None, int | None]:
    """Static telemetry text, the featured dish and the column of its status word."""
    g = Grid(PANEL_COLS, PANEL_ROWS)
    W = PANEL_COLS
    g.put(0, 0, "MDSCC · ROBLEDO DE CHAVELA", "b")
    g.put(2, 0, "─" * W, "n")
    g.put(16, 0, "─" * W, "n")
    g.put(21, 2, "LIVE · eyes.nasa.gov/dsn", "d")
    if snap is None:
        g.put(1, 0, "40.24°N  4.25°W", "d")
        g.put(3, 0, "NO SIGNAL", "r")
        g.put(5, 0, "DSN Now feed unreachable at build time", "d")
        return g, None, None

    lat, lon = snap["lat"], snap["lon"]
    g.put(1, 0, f"{abs(lat):.2f}°{'N' if lat >= 0 else 'S'}  {abs(lon):.2f}°{'W' if lon < 0 else 'E'}", "d")
    stamp = snap["time"].strftime("%Y-%m-%d %H:%M UTC")
    g.put(1, W - len(stamp), stamp, "d")

    feat, state_col = _featured(snap["dishes"]), None
    if feat is None:
        g.put(3, 0, "ALL ANTENNAS IDLE", "d")
    else:
        name, size = _dish_label(feat)
        g.put(3, 0, name)
        g.put(3, len(name), f" · {size}" if size else "", "d")
        state = "TRACKING" if feat["down"] else "UPLINK" if feat["up"] else "POINTED"
        state_col = W - len(state)
        g.put(3, state_col, state, "g")
        tgt = feat["targets"][0]
        g.put(5, 0, "TARGET", "d")
        g.put(5, 9, tgt["name"], "b")
        if tgt["friendly"].lower() not in ("", tgt["name"].lower()):
            g.put(6, 9, tgt["friendly"][:W - 9])
        g.put(7, 0, "AZ / EL", "d")
        g.put(7, 9, f"{feat['az']:.1f}° / {feat['el']:.1f}°")
        if feat["wind"] >= 0:
            wind = f"{feat['wind']:.0f} km/h"
            g.put(7, W - len(wind) - 5, "WIND", "d")
            g.put(7, W - len(wind), wind)
        g.put(8, 0, "DOWN", "d")
        if feat["down"]:
            s = feat["down"][0]
            g.put(8, 9, f"{s['band']}-band", "b")
            g.put(8, 17, _rate(s["rate"]))
            if s["power"] < 0:
                p = f"{s['power']:.0f} dBm"
                g.put(8, W - len(p), p)
        else:
            g.put(8, 9, "—", "d")
        g.put(9, 0, "UP", "d")
        if feat["up"]:
            s = feat["up"][0]
            g.put(9, 9, f"{s['band']}-band", "b")
            if s["power"] > 0:
                g.put(9, 17, f"{s['power']:.1f} kW")
        else:
            g.put(9, 9, "—", "d")
        g.put(10, 0, "RTLT", "d")
        g.put(10, 9, _rtlt(tgt["rtlt"]))
        rng = _range(tgt["range"])
        g.put(10, W - len(rng) - 6, "RANGE", "d")
        g.put(10, W - len(rng), rng)
        g.put(11, 0, "DOWNLINK SPECTRUM", "d")
        label = "carrier + data sidebands" if feat["down"] else "noise floor"
        g.put(11, W - len(label), label, "n")

    others = [d for d in snap["dishes"] if d is not feat][:4]
    for i, d in enumerate(others):
        r = 17 + i
        name, size = _dish_label(d)
        g.put(r, 0, name)
        g.put(r, 7, size, "d")
        if d["targets"]:
            g.put(r, 13, d["targets"][0]["name"][:10], "b")
            if d["down"]:
                s = d["down"][0]
                g.put(r, 25, f"{s['band']}↓", "d")
                g.put(r, 28, _rate(s["rate"]))
        else:
            act = ACTIVITY.get(d["activity"], d["activity"].lower() or "idle")
            g.put(r, 13, "· " + act[:W - 15], "d")
    return g, feat, state_col


def _spectrum(rnd: random.Random, carrier: bool, x0: float, y0: float, w: float, h: float,
              clock: Clock, n: int = 12, dt: int = 150, points: int = 110) -> list[str]:
    """Analyzer trace: residual carrier plus sinc^2 data sidebands over a noise floor."""
    x = np.linspace(-23, 23, points)
    px = x0 + (x + 23) / 46 * w
    out = [f'<path d="M{num(x0)} {num(y0 + h * k / 3)}h{num(w)}" class="grat"/>' for k in range(3)]
    out.append(f'<path d="M{num(x0 + w / 2)} {num(y0)}v{num(h)}" class="grat"/>')
    for i in range(n):
        val = 0.07 + 0.09 * np.array([rnd.random() for _ in x])
        if carrier:
            val += 0.9 * np.exp(-(x / 0.45) ** 2)
            for c in (-10, 10):
                val += 0.48 * (0.92 + 0.16 * rnd.random()) * np.sinc((x - c) / 3.4) ** 2
        py = y0 + h * (1 - np.clip(val, 0, 1))
        trace = " ".join(f"{num(a)} {num(b)}" for a, b in zip(px, py))
        style = clock.cycle(i * dt, (i + 1) * dt, n * dt)
        out.append(f'<path d="M{num(x0)} {num(y0 + h)}L{trace}L{num(x0 + w)} {num(y0 + h)}Z" '
                   f'class="tr{"" if carrier else " nf"} k" style="{style}"/>')
    return out


def _ticker(rnd: random.Random, carrier: bool, period: int = 24) -> list[Grid]:
    stream = ASM + [f"{rnd.randrange(256):02X}" for _ in range(period - len(ASM))]
    shown = (PANEL_COLS - 5) // 3
    frames = []
    for i in range(period if carrier else 1):
        g = Grid(PANEL_COLS, PANEL_ROWS)
        g.put(TICKER_ROW, 0, "RX ›", "d")
        for j in range(shown):
            k = (i + j) % period
            byte = stream[k] if carrier else "--"
            g.put(TICKER_ROW, 5 + 3 * j, byte, "g" if carrier and k < len(ASM) else "d")
        frames.append(g)
    return frames


def build(theme: str, snap: dict | None) -> str:
    rnd = random.Random(1966)          # first light at Robledo's predecessor
    t = THEMES[theme]
    clock = Clock()
    panel, feat, state_col = _panel(snap)
    carrier = bool(feat and feat["down"])
    el = feat["el"] if feat and 0 < feat["el"] <= 90 else 90.0

    ant = dish3d.Antenna(el)
    cam = dish3d.Camera(DISH_COLS, DISH_ROWS, DISH_CW, DISH_LH)
    dish_frames, sky = [], np.ones((DISH_ROWS, DISH_COLS), bool)
    for i in range(DISH_FRAMES):
        az = 200 + 360 * i / DISH_FRAMES
        phase = (3 * i / DISH_FRAMES) % 1.0
        chars, classes = dish3d.render(ant, cam, az, phase if carrier else None,
                                       invert=theme == "light")
        g = Grid(DISH_COLS, DISH_ROWS)
        g.ch, g.cl = chars, classes
        sky &= np.array(chars) == " "
        dish_frames.append(g)

    dish_ys = [DISH_Y + (r + 1) * DISH_LH - 2 for r in range(DISH_ROWS)]
    panel_ys = [PANEL_Y + (r + 1) * PANEL_LH - 5 for r in range(PANEL_ROWS)]
    height = max(dish_ys[-1], panel_ys[-1]) + 22

    body = []
    for r in range(int(DISH_ROWS * 0.62)):
        for c in range(DISH_COLS):
            if sky[r, c] and rnd.random() < 0.02:
                star = rnd.choice("··········+*")
                body.append(f'<text x="{num(DISH_X + c * DISH_CW)}" y="{num(dish_ys[r])}" '
                            f'class="s tw d" style="animation-delay:-{rnd.randrange(4000)}ms">'
                            f'{star}</text>')
    body += animate_frames(dish_frames, DISH_DT, DISH_X, dish_ys, DISH_CW, clock, cls="s")
    body.append(f'<line x1="{PANEL_X - 14}" x2="{PANEL_X - 14}" y1="22" y2="{num(height - 22)}" '
                f'class="sep"/>')
    body += [text_el(panel.runs(r), PANEL_X, panel_ys[r], PANEL_CW, ' class="m"')
             for r in range(PANEL_ROWS)]
    spec_top = PANEL_Y + SPEC_ROW * PANEL_LH + 2
    body += _spectrum(rnd, carrier, PANEL_X, spec_top, PANEL_COLS * PANEL_CW,
                      3 * PANEL_LH - 8, clock)
    tick = _ticker(rnd, carrier)
    body += animate_rows(tick, [160] * len(tick), PANEL_X, panel_ys, PANEL_CW, clock,
                         cls="m", loop=len(tick) > 1)
    if state_col is not None:
        body.append(f'<text x="{num(PANEL_X + (state_col - 2) * PANEL_CW)}" '
                    f'y="{num(panel_ys[3])}" class="m g blink">●</text>')
    body.append(f'<text x="{num(PANEL_X)}" y="{num(panel_ys[21])}" '
                f'class="m {"g" if snap else "r"} blink">●</text>')

    css = (f".s{{font-size:{DISH_FS}px}}.m{{font-size:{PANEL_FS}px}}"
           f".sep{{stroke:{t['border']}}}.grat{{stroke:{t['border']};stroke-dasharray:2 4}}"
           f".tr{{fill:{t['green']};fill-opacity:.14;stroke:{t['green']};stroke-width:1.2;"
           f"stroke-linejoin:round}}.nf{{fill:{t['dim']};stroke:{t['dim']}}}"
           "@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}"
           ".blink{animation:blink 1.6s ease-in-out infinite}"
           "@keyframes tw{0%,100%{opacity:.9}50%{opacity:.15}}"
           ".tw{animation:tw 4s ease-in-out infinite}" + clock.css())
    return svg_doc(WIDTH, height, theme, [b for b in body if b], css,
                   title="Live from DSN Madrid")
