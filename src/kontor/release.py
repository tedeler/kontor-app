"""Kommandozeile der Release-CI (D-105): ``python -m kontor.release hochzaehlen|build``."""

from __future__ import annotations

import json

from .version import naechste


def hochzaehlen(datei: str, major: bool = False) -> str:
    """Schreibt die nächste Version in ``datei`` (Release-CI) und gibt sie zurück."""
    from pathlib import Path
    pfad = Path(datei)
    neu = naechste(pfad.read_text(encoding="utf-8"), major=major)
    pfad.write_text(neu + "\n", encoding="utf-8")
    return neu


def build_schreiben(datei: str, commit: str, build_datum: str) -> None:
    """Schreibt ``build.json`` (Release-CI)."""
    from pathlib import Path
    Path(datei).write_text(json.dumps({"commit": commit, "build_datum": build_datum}) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="python -m kontor.release", description="Versionsnummer für die Release-CI")
    u = p.add_subparsers(dest="befehl", required=True)
    h = u.add_parser("hochzaehlen", help="Minor (oder mit --major Major) in der VERSION-Datei erhöhen")
    h.add_argument("datei")
    h.add_argument("--major", action="store_true")
    b = u.add_parser("build", help="build.json schreiben")
    b.add_argument("datei")
    b.add_argument("--commit", required=True)
    b.add_argument("--datum", required=True)
    a = p.parse_args(argv)
    if a.befehl == "hochzaehlen":
        print(hochzaehlen(a.datei, major=a.major))
    else:
        build_schreiben(a.datei, a.commit, a.datum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
