"""Live snapshot of the Madrid Deep Space Communications Complex from NASA's DSN Now feed."""
from __future__ import annotations

import datetime as dt
import urllib.request
import xml.etree.ElementTree as ET

DSN_URL = "https://eyes.nasa.gov/dsn/data/dsn.xml"
CONFIG_URL = "https://eyes.nasa.gov/dsn/config.xml"
SITE = "mdscc"
PLACEHOLDERS = {"DSN", "DSS", ""}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "RaymonDev-profile/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def _num(v: str | None) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return -1.0


def _signals(dish: ET.Element, tag: str) -> list[dict]:
    return [{"band": s.get("band", ""), "rate": _num(s.get("dataRate")),
             "power": _num(s.get("power")), "spacecraft": s.get("spacecraft", "")}
            for s in dish.findall(tag)
            if s.get("active") == "true" and s.get("spacecraft", "") not in PLACEHOLDERS]


def madrid() -> dict:
    cfg = ET.fromstring(_get(CONFIG_URL))
    names = {sc.get("name", "").lower(): sc.get("friendlyName", "") for sc in cfg.iter("spacecraft")}
    site = next(s for s in cfg.iter("site") if s.get("name") == SITE)
    types = {d.get("name"): d.get("type", "") for d in site.iter("dish")}

    feed = ET.fromstring(_get(DSN_URL))
    station, current, dishes = None, None, []
    for el in feed:
        if el.tag == "station":
            current = el.get("name")
            if current == SITE:
                station = el
        elif el.tag == "dish" and current == SITE:
            targets = [{"name": t.get("name", ""), "rtlt": _num(t.get("rtlt")),
                        "range": _num(t.get("downlegRange"))}
                       for t in el.findall("target") if t.get("name", "") not in PLACEHOLDERS]
            for t in targets:
                t["friendly"] = names.get(t["name"].lower(), "")
            dishes.append({
                "name": el.get("name", ""), "type": types.get(el.get("name"), ""),
                "az": _num(el.get("azimuthAngle")), "el": _num(el.get("elevationAngle")),
                "wind": _num(el.get("windSpeed")), "activity": el.get("activity", ""),
                "up": _signals(el, "upSignal"), "down": _signals(el, "downSignal"),
                "targets": targets,
            })
    ms = _num(station.get("timeUTC")) if station is not None else -1
    when = (dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc) if ms > 0
            else dt.datetime.now(dt.timezone.utc))
    return {"site": site.get("friendlyName", "Madrid"), "lat": _num(site.get("latitude")),
            "lon": _num(site.get("longitude")), "time": when, "dishes": dishes}
