"""ASCII renderer for a Cassegrain dish on an alt-az mount.

The antenna is a cloud of sampled surface points. Each frame rotates it in
azimuth, projects it with perspective, keeps the nearest point per character
cell (z-buffer) and shades it with Lambert lighting mapped onto a luminance
ramp, the same trick as donut.c.
"""
from __future__ import annotations

import math

import numpy as np

SURF, STRUT, WAVE, GROUND = range(4)

R = 1.0                 # main reflector radius
F = 0.6                 # focal length
H = 1.35                # elevation axis height
VX = 0.30               # reflector vertex, in front of the elevation axis
SUB_X = VX + F - 0.08   # subreflector on the boresight
SUB_R = 0.14

RAMP = ".,-~:;=!*#$@"


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


class Cloud:
    def __init__(self):
        self.parts = []

    def add(self, p, n, kind, alb=1.0):
        p = np.asarray(p, float).reshape(-1, 3)
        n = np.zeros_like(p) if n is None else np.asarray(n, float).reshape(-1, 3)
        n = np.broadcast_to(n, p.shape)
        alb = np.broadcast_to(np.asarray(alb, float).ravel(), (len(p),))
        self.parts.append((p, n, np.full(len(p), kind), alb))

    def arrays(self):
        return [np.concatenate(a) for a in zip(*self.parts)]


def _polar(nr, nphi, r0=0.0, r1=1.0):
    r = np.sqrt(np.linspace(r0 ** 2, r1 ** 2, nr))
    phi = np.linspace(0, 2 * np.pi, nphi, endpoint=False)
    return np.meshgrid(r, phi)


def _reflector(c: Cloud):
    r, phi = _polar(90, 320, 0.11 * R, R)
    y, z = r * np.cos(phi), r * np.sin(phi)
    x = VX + r ** 2 / (4 * F)
    n = np.stack([np.ones_like(x), -y / (2 * F), -z / (2 * F)], -1)
    seam = (np.abs((r / R * 4) % 1 - 0.5) > 0.45) | (np.abs((phi / np.pi * 8) % 1 - 0.5) > 0.47)
    c.add(np.stack([x, y, z], -1), _unit(n), SURF, np.where(seam, 0.78, 1.0))


def _cone(c: Cloud, x0, r0, x1, r1, nu=30, nphi=140):
    u, phi = np.meshgrid(np.linspace(0, 1, nu), np.linspace(0, 2 * np.pi, nphi, endpoint=False))
    x, rr = x0 + (x1 - x0) * u, r0 + (r1 - r0) * u
    p = np.stack([x, rr * np.cos(phi), rr * np.sin(phi)], -1)
    n = np.stack([np.full_like(x, -(r1 - r0)), (x1 - x0) * np.cos(phi), (x1 - x0) * np.sin(phi)], -1)
    c.add(p, _unit(n), SURF)


def _disk(c: Cloud, x, radius, bulge=0.0, n=24, nphi=90):
    r, phi = _polar(n, nphi, 0, radius)
    y, z = r * np.cos(phi), r * np.sin(phi)
    c.add(np.stack([np.full_like(y, x), y, z], -1),
          _unit(np.stack([-np.ones_like(y), bulge * y, bulge * z], -1)), SURF)


def _line(c: Cloud, a, b, n=160):
    a, b = np.asarray(a, float), np.asarray(b, float)
    t = np.linspace(0, 1, n)[:, None]
    c.add(a + (b - a) * t, b - a, STRUT)


def _quad(c: Cloud, a, b, cc, d, nu=40, nv=40):
    """Bilinear patch a-b-cc-d (counter-clockwise seen from outside)."""
    a, b, cc, d = (np.asarray(v, float) for v in (a, b, cc, d))
    u, v = np.meshgrid(np.linspace(0, 1, nu), np.linspace(0, 1, nv))
    u, v = u[..., None], v[..., None]
    p = (1 - v) * ((1 - u) * a + u * b) + v * ((1 - u) * d + u * cc)
    c.add(p, _unit(np.cross(b - a, d - a)), SURF)


def _frustum(c: Cloud, z0, z1, hx0, hy0, hx1, hy1, top=True):
    lo = [(-hx0, -hy0, z0), (hx0, -hy0, z0), (hx0, hy0, z0), (-hx0, hy0, z0)]
    hi = [(-hx1, -hy1, z1), (hx1, -hy1, z1), (hx1, hy1, z1), (-hx1, hy1, z1)]
    for i in range(4):
        j = (i + 1) % 4
        _quad(c, lo[i], lo[j], hi[j], hi[i])
    if top:
        _quad(c, hi[0], hi[1], hi[2], hi[3])


def _cylinder_z(c: Cloud, radius, z0, z1, nz=12, nphi=160):
    z, phi = np.meshgrid(np.linspace(z0, z1, nz), np.linspace(0, 2 * np.pi, nphi, endpoint=False))
    p = np.stack([radius * np.cos(phi), radius * np.sin(phi), z], -1)
    c.add(p, np.stack([np.cos(phi), np.sin(phi), np.zeros_like(z)], -1), SURF)
    r, phi = _polar(14, nphi, 0, radius)
    c.add(np.stack([r * np.cos(phi), r * np.sin(phi), np.full_like(r, z1)], -1), (0, 0, 1), SURF)


def _elevate(v, el, point=True):
    ce, se = math.cos(el), math.sin(el)
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    out = np.stack([x * ce - z * se, y, x * se + z * ce], -1)
    if point:
        out[:, 2] += H
    return out


def _azimuth(v, az):
    ca, sa = math.cos(az), math.sin(az)
    x, y = v[:, 0], v[:, 1]
    return np.stack([x * ca - y * sa, x * sa + y * ca, v[:, 2]], -1)


class Antenna:
    def __init__(self, elevation_deg: float):
        self.el = math.radians(elevation_deg)
        dish = Cloud()
        _reflector(dish)
        _cone(dish, 0.05, 0.17, VX + 0.17, 0.66)          # back-up truss
        _cone(dish, -0.05, 0.17, 0.05, 0.17, nu=8)        # hub
        _disk(dish, -0.05, 0.17)
        _cone(dish, VX + 0.01, 0.09, VX + 0.24, 0.045, nu=12, nphi=60)   # feed horn
        _disk(dish, SUB_X, SUB_R, bulge=1.6)
        for k in range(4):
            phi = math.pi / 4 + k * math.pi / 2
            rim = 0.96 * R
            _line(dish, (VX + rim ** 2 / (4 * F), rim * math.cos(phi), rim * math.sin(phi)),
                  (SUB_X, SUB_R * math.cos(phi), SUB_R * math.sin(phi)))
        p, n, kind, alb = dish.arrays()
        p, n = _elevate(p, self.el), _elevate(n, self.el, point=False)

        mount = Cloud()
        _cylinder_z(mount, 0.62, 0.0, 0.16)                       # azimuth track / pad
        _frustum(mount, 0.16, H - 0.18, 0.40, 0.44, 0.24, 0.30)   # alidade
        for side in (-1, 1):                                      # yoke arms
            _frustum_arm(mount, side * 0.38)
        for dz in (-0.04, 0.0, 0.04):
            _line(mount, (0, -0.46, H + dz), (0, 0.46, H + dz), n=60)
        mp, mn, mk, ma = mount.arrays()
        self.p = np.concatenate([p, mp])
        self.n = np.concatenate([n, mn])
        self.kind = np.concatenate([kind, mk])
        self.alb = np.concatenate([alb, ma])

        gx, gy = np.meshgrid(np.linspace(-2.1, 2.1, 13), np.linspace(-2.1, 2.1, 13))
        keep = gx ** 2 + gy ** 2 <= 2.15 ** 2
        self.ground = np.stack([gx[keep], gy[keep], np.zeros(keep.sum())], -1)

    def waves(self, phase: float, rings: int = 3, travel: float = 1.05):
        """Wavefronts leaving the dish along the boresight; alb holds their age."""
        pts, ages = [], []
        phi = np.linspace(0, 2 * np.pi, 220, endpoint=False)
        for k in range(rings):
            age = (phase + k / rings) % 1.0
            rad = (0.62 - 0.24 * age) * R
            ring = np.stack([np.full_like(phi, SUB_X + 0.05 + age * travel),
                             rad * np.cos(phi), rad * np.sin(phi)], -1)
            pts.append(ring)
            ages.append(np.full(len(phi), age))
        return _elevate(np.concatenate(pts), self.el), np.concatenate(ages)


def _frustum_arm(c: Cloud, y):
    _frustum_offset(c, y, H - 0.32, H + 0.08, 0.10, 0.05)


def _frustum_offset(c: Cloud, y, z0, z1, hx, hy):
    lo = [(-hx, y - hy, z0), (hx, y - hy, z0), (hx, y + hy, z0), (-hx, y + hy, z0)]
    hi = [(-hx, y - hy, z1), (hx, y - hy, z1), (hx, y + hy, z1), (-hx, y + hy, z1)]
    for i in range(4):
        j = (i + 1) % 4
        _quad(c, lo[i], lo[j], hi[j], hi[i], nu=8, nv=16)
    _quad(c, hi[0], hi[1], hi[2], hi[3], nu=8, nv=8)


class Camera:
    def __init__(self, cols, rows, cw, lh, *, target=(0.0, 0.0, 1.3), dist=7.5,
                 elev_deg=13.0, azim_deg=-90.0, px_per_unit=118.0, centre=(0.5, 0.52)):
        self.cols, self.rows, self.cw, self.lh = cols, rows, cw, lh
        e, a = math.radians(elev_deg), math.radians(azim_deg)
        self.target = np.array(target)
        self.pos = self.target + dist * np.array([math.cos(e) * math.cos(a),
                                                  math.cos(e) * math.sin(a), math.sin(e)])
        self.fwd = _unit(self.target - self.pos)
        self.right = _unit(np.cross(self.fwd, [0, 0, 1]))
        self.up = np.cross(self.right, self.fwd)
        self.focal = px_per_unit * dist
        self.cx, self.cy = cols * centre[0], rows * centre[1]
        # light from the upper left, slightly behind the viewer
        self.light = _unit(-0.45 * self.right + 0.6 * self.up - 0.65 * self.fwd)

    def project(self, p):
        v = p - self.pos
        z = v @ self.fwd
        col = self.cx + (v @ self.right) / z * self.focal / self.cw
        row = self.cy - (v @ self.up) / z * self.focal / self.lh
        return col, row, z


def _strut_chars(cam: Camera, p, d):
    c0, r0, _ = cam.project(p)
    c1, r1, _ = cam.project(p + d * 0.02)
    ang = np.degrees(np.arctan2(-(r1 - r0) * cam.lh, (c1 - c0) * cam.cw)) % 180
    return np.select([ang < 22.5, ang < 67.5, ang < 112.5, ang < 157.5],
                     ["-", "/", "|", "\\"], "-")


def render(ant: Antenna, cam: Camera, az_deg: float, phase: float | None, invert: bool = False):
    """One frame: (chars, classes) as lists of rows; phase None means no wavefronts."""
    az = math.radians(az_deg)
    wp, wage = ant.waves(phase) if phase is not None else (np.zeros((0, 3)), np.zeros(0))
    p = np.concatenate([_azimuth(ant.p, az), _azimuth(wp, az), ant.ground])
    n = np.concatenate([_azimuth(ant.n, az), np.zeros_like(wp), np.zeros_like(ant.ground)])
    kind = np.concatenate([ant.kind, np.full(len(wp), WAVE), np.full(len(ant.ground), GROUND)])
    alb = np.concatenate([ant.alb, wage, np.zeros(len(ant.ground))])

    col, row, z = cam.project(p)
    ci, ri = np.floor(col).astype(int), np.floor(row).astype(int)
    ok = (z > 0.1) & (ci >= 0) & (ci < cam.cols) & (ri >= 0) & (ri < cam.rows)
    idx = np.flatnonzero(ok)
    idx = idx[np.argsort(z[idx], kind="stable")]
    cell = ri[idx] * cam.cols + ci[idx]
    _, first = np.unique(cell, return_index=True)
    win = idx[first]

    chars = np.full(cam.rows * cam.cols, " ", dtype="<U1")
    classes = np.full(cam.rows * cam.cols, "", dtype="<U1")
    cells = ri[win] * cam.cols + ci[win]
    k = kind[win]

    ramp = np.array(list(RAMP[::-1] if invert else RAMP))
    s = k == SURF
    nn = n[win[s]]
    towards = cam.pos - p[win[s]]
    nn = np.where(((nn * towards).sum(-1) < 0)[:, None], -nn, nn)
    view = _unit(towards)
    diff = np.clip(nn @ cam.light, 0, 1)
    refl = 2 * diff[:, None] * nn - cam.light
    spec = np.clip((refl * view).sum(-1), 0, 1) ** 18
    lum = np.clip(0.14 + 0.74 * diff + 0.5 * spec, 0, 1) * alb[win[s]]
    chars[cells[s]] = ramp[np.clip((lum * len(ramp)).astype(int), 0, len(ramp) - 1)]

    s = k == STRUT
    chars[cells[s]] = _strut_chars(cam, p[win[s]], n[win[s]])
    classes[cells[s]] = "d"

    s = k == WAVE
    age = alb[win[s]]
    chars[cells[s]] = np.where(age < 0.34, "o", np.where(age < 0.67, "°", "·"))
    classes[cells[s]] = np.where(age < 0.67, "b", "d")

    s = k == GROUND
    chars[cells[s]] = "."
    classes[cells[s]] = "n"

    chars = chars.reshape(cam.rows, cam.cols)
    classes = classes.reshape(cam.rows, cam.cols)
    return ([list(r) for r in chars],
            [[c or None for c in r] for r in classes])
