"""WEGWERF-REFERENZ der Selbstprüfung – KEIN Anwendungscode.

Diese Mini-Implementierung existiert nur, um zu zeigen, dass die mit
``kern`` markierten Tests bei richtiger Logik grün und bei eingebauten
Fehlern (Mutanten, Umgebungsvariable ``KONTOR_MUTANT``) rot werden. Sie
deckt nur die Kernfunktionen ab (Buchhaltung, Salden, Splits, Import,
Dubletten, Filter, Mehrfachbearbeitung; ab M2 Synchronisation mit dem
Mock-Bank-Plugin, TAN, PIN, Planer, Regeln und Vorschläge), hält alles im
Arbeitsspeicher und ist weder vollständig noch für den Betrieb gedacht.
"""

import os

MUTANT = os.environ.get("KONTOR_MUTANT", "")

#: Schema MAJOR.MINOR (version.md 1.1); der Mutant schreibt Minor ohne führende Null (PEP-440-normalisiert)
__version__ = "0.7" if MUTANT == "m13_version_normalisiert" else "0.07"


def mutant(name: str) -> bool:
    return MUTANT == name
