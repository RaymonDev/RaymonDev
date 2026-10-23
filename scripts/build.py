"""Build the profile SVGs into dist/; --preview also writes an offline preview page."""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

import dsn
import header
import station

HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(HERE.parent / "dist"))
    ap.add_argument("--preview", action="store_true", help="also write preview.html")
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        snap = dsn.madrid()
    except Exception as e:             # the card still renders, as "no signal"
        print(f"DSN feed unavailable: {e}", file=sys.stderr)
        snap = None

    for theme in ("dark", "light"):
        for name, svg in (("header", header.build(theme)), ("station", station.build(theme, snap))):
            path = out / f"{name}-{theme}.svg"
            path.write_text(svg, encoding="utf-8")
            print(f"{path.name:20} {len(svg.encode()) / 1024:7.1f} KiB")
    if args.preview:
        shutil.copy(HERE / "preview.html", out / "preview.html")
        print(f"preview: {out / 'preview.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
