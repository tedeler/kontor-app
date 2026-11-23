"""Selbstprüfung der Tests gegen eine Wegwerf-Referenz mit eingebauten Fehlern (Mutanten).

Aufruf im Wurzelverzeichnis von kontor-tests:

    python -m tests._selbstpruefung                 # Referenz + alle Mutanten
    python -m tests._selbstpruefung --nur-referenz  # nur die grünen Läufe (ohne und mit Zusatzfeldern, E-124)
    python -m tests._selbstpruefung --mutant filter_ohne_umlaute
    python -m tests._selbstpruefung --protokoll tests/_selbstpruefung/LETZTER_LAUF.md

Ablauf: Die Kern-Tests (``pytest -m kern tests/app``) laufen in einem
Unterprozess, in dem das Paket ``kontor`` aus ``tests/_selbstpruefung/referenz``
kommt (PYTHONPATH). Ohne Mutant müssen alle Kern-Tests bestehen; mit jedem
Mutanten muss mindestens ein Kern-Test fehlschlagen. Normale Testläufe sammeln
dieses Verzeichnis nie ein (pytest.ini ``norecursedirs``, conftest
``collect_ignore_glob``).
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
REPO = HIER.parents[1]
REFERENZ = HIER / "referenz"

MUTANTEN: dict[str, str] = {
    "saldo_stichtag_exklusiv": "Stichtag der Kontenübersicht schließt den Tag selbst aus",
    "saldo_gesamt_nur_kinder": "saldo_gesamt summiert nur direkte Unterkonten, nicht rekursiv",
    "split_summe_ungeprueft": "Buchungen mit Splitsumme ≠ 0 werden angenommen",
    "ein_split_erlaubt": "Buchungen mit nur einem Split werden angenommen",
    "betrag_float": "Gleitkommazahlen werden als Betrag akzeptiert",
    "betrag_umsatz_abs": "Umsatz = Betrag des ersten Splits statt Summe der positiven Splits",
    "kategorie_memo_verloren": "Kategorie setzen löscht das Memo des Gegensplits",
    "mehrfach_nicht_atomar": "Mehrfachbearbeitung ändert gültige Buchungen, bevor sie den Fehler meldet",
    "import_teilimport": "Bei Inhaltsfehlern werden Empfänger trotzdem angelegt (Teilimport)",
    "import_ohne_ausgleich": "Unausgeglichene KMyMoney-Transaktionen werden nicht ausgeglichen",
    "idempotenz_buchungen": "Zweiter Import erkennt Buchungen nicht über extern_ids",
    "idempotenz_empfaenger": "Zweiter Import legt Empfänger erneut an",
    "dublette_ohne_eindeutigkeit": "Zusammenführen, obwohl der Kandidat auch eine andere neue Buchung trifft",
    "dublette_erster_kandidat": "Bei mehreren exakten Kandidaten wird mit dem ersten zusammengeführt",
    "dublette_empfaenger_exakt": "Empfängervergleich exakt statt nach ekey (Umlaute, Schreibweise)",
    "dublette_ohne_toleranz": "Ähnliche Kandidaten nur am selben Tag statt ±3 Tage",
    "filter_ohne_umlaute": "Freitext/Verwendungszweck ohne Umlautnormalisierung",
    "filter_bis_exklusiv": "Filter bis schließt den Tag selbst aus",
    "unterkategorien_ignoriert": "kategorie_id mit unterkategorien=true berücksichtigt keine Unterkonten",
    "sortierung_instabil": "Gleichstand in der Sortierung nach id absteigend statt aufsteigend",
    # Meilenstein 2
    "sync_ohne_kennung": "M2: Umsatzkennungen werden nicht geprüft (wiederholter Abruf bucht doppelt)",
    "sync_geloeschte_wieder": "M2: nur Kennungen vorhandener Buchungen zählen (Gelöschtes kommt wieder)",
    "sync_vormerkung_gebucht": "M2: Vormerkungen werden gebucht",
    "sync_kein_abgleich": "M2: kein Abgleich mit vorhandenen Buchungen beim Abruf",
    "sync_von_ohne_ueberlappung": "M2: Folgeabruf beginnt am Tag nach dem letzten Abruf statt mit Überlappung",
    "benachrichtigung_flut": "M2: gleiche Fehler erzeugen jedes Mal eine neue Benachrichtigung",
    "regel_prioritaet_umgekehrt": "M2: größte statt kleinste Priorität gewinnt",
    "regel_gleichstand_spaeter": "M2: bei gleicher Priorität gewinnt die später angelegte Regel",
    "regel_ohne_umlaute": "M2: Regeltexte nur casefold, ohne Umlautnormalisierung",
    "regel_inaktiv_greift": "M2: inaktive Regeln werden angewendet",
    "regelbetrag_absolut": "M2: Betragsbedingungen vergleichen den Absolutbetrag",
    "vorschlag_nicht_markiert": "M2: Regeltreffer werden nicht als Vorschlag markiert",
    "ablehnen_ohne_ruecksetzen": "M2: Ablehnen lässt die vorgeschlagene Kategorie stehen",
    "tan_ablauf_ignoriert": "M2: abgelaufene TAN-Anforderungen bleiben offen",
    "pin_nicht_verworfen": "M2: falsche PIN bleibt gespeichert",
    "pin_im_fehlertext": "M2: die abgelehnte PIN steht in der Fehlermeldung",
    "planer_ohne_wiederholung": "M2: nach Fehlschlag wartet der Planer das volle Intervall statt des Wiederholungsabstands",
    "neustart_ohne_abbruch": "M2: Neustart lässt wartende Läufe und offene TAN-Anforderungen bestehen",
    # Meilenstein 3: Konten mit Buchungen löschen (loeschen.md)
    "loeschen_sperre_ignoriert": "M3: abgeglichene Buchungen werden ohne Bestätigung gelöscht/umgebucht",
    "loeschen_unterkonten_wurzel": "M3: Unterkonten werden Wurzelkonten statt eine Ebene nach oben zu rücken",
    "loeschen_vorschlag_bleibt": "M3: umgebuchte Buchungen behalten ihren Vorschlag",
    "loeschen_ohne_konflikt": "M3: Konfliktbuchungen (Quelle und Ziel gleich) werden nicht erkannt",
    "loeschen_ohne_zusammenfassen": "M3: Splits auf dem Zielkonto werden nicht zusammengefasst",
    "loeschen_trocken_schreibt": "M3: der Probelauf schreibt die Änderungen doch",
    "loeschen_abstimmung_bleibt": "M3: Abstimmungen des gelöschten Kontos bleiben bestehen",
    # Meilenstein 3, Nachtrag: gelöschte Bankkonten (synchronisation.md 16)
    "sync_geloeschtes_neu": "M3: ein gelöschtes Bankkonto wird beim Abruf still und leer neu angelegt",
    "wiederherstellen_ohne_vergessen": "M3: Wiederherstellen mit \"alle\" vergisst die Kennungen nicht",
    "wiederherstellen_vergisst_alle": "M3: Wiederherstellen vergisst auch Kennungen noch existierender Buchungen",
    "wiederherstellen_zeitraum_bleibt": "M3: Wiederherstellen setzt letzter_abruf_bis nicht zurück",
    "undo_wiederherstellung_eintrag_weg": "M3: Rückgängig der Wiederherstellung entfernt den Sync-Eintrag",
    # Meilenstein 3: Protokoll, Rückgängig, Empfänger, Umbuchungen, Abstimmung, Suche
    "protokoll_fehlt_mehrfach_tags": "M3: Mehrfachbearbeitung der Tags wird nicht protokolliert",
    "protokoll_sync_fehlt": "M3: die Übernahme der Umsätze eines Kontos wird nicht protokolliert",
    "aenderung_ohne_wirkung": "M3: Operationen ohne Wirkung erzeugen trotzdem eine Änderung",
    "undo_ohne_zustandspruefung": "M3: Rückgängig überschreibt spätere Änderungen derselben Objekte",
    "undo_ohne_bezugspruefung": "M3: Rückgängig prüft Bezüge und Eindeutigkeit nicht",
    "undo_splits_neue_ids": "M3: wiederhergestellte Buchungen erhalten neue Split-IDs",
    "undo_kennungen_bleiben": "M3: Rückgängig eines Abrufs vergisst die gemerkten Umsatzkennungen nicht",
    "alias_ohne_ekey": "M3: Aliase werden exakt statt nach ekey verglichen",
    "zusammenfuehren_ohne_alias": "M3: Zusammenführen übernimmt Namen und Aliase der Quellen nicht",
    "umbuchung_ohne_iban": "M3: Umbuchungen ohne Prüfung der Gegen-IBAN (auch an fremde IBAN)",
    "umbuchung_ohne_eindeutigkeit": "M3: Umbuchungspaare ohne gegenseitige Eindeutigkeit",
    "umbuchung_fenster_exklusiv": "M3: das Zeitfenster der Umbuchung schließt den letzten Tag aus",
    "abstimmung_trotz_differenz": "M3: die Abstimmung markiert auch bei Differenz",
    "abstimmung_ohne_sperre": "M3: abgestimmte Buchungen sind nicht gesperrt",
    "abstimmung_stichtag_exklusiv": "M3: die Abstimmung schließt den Stichtag aus",
    "suche_ohne_akzente": "M3: Volltextsuche ohne Akzentfaltung (Café ≠ Cafe)",
    "suche_oder": "M3: Volltextsuche verknüpft die Wörter mit ODER",
    "suche_ohne_nfc": "M3: Volltextsuche ohne NFC (zerlegte Umlaute)",
    # Meilenstein 9: Datensicherung (sicherung.md)
    "sicherung_mit_protokoll": "M9: die Sicherung enthält das Änderungsprotokoll",
    "sicherung_ohne_kennungen": "M9: gemerkte Umsatzkennungen werden weder gesichert noch ersetzt",
    "sicherung_sync_konten_bleiben": "M9: der Zustand je Bankkonto wird beim Einspielen nicht ersetzt",
    "sicherung_zaehler_nicht_uebernommen": "M9: ID-Zähler der Sicherung werden nicht übernommen (IDs doppelt vergeben)",
    "sicherung_db_pruefsumme_ungeprueft": "M9: datenbank_sha256 wird nicht geprüft",
    "sicherung_fremde_tabellen_erlaubt": "M9: Views, Trigger und fremde Tabellen in der Sicherung werden angenommen",
    "sicherung_pruefsumme_ungeprueft": "M9: Anzahlen und inhalt_sha256 werden nicht geprüft",
    "sicherung_modus_ungeprueft": "M9: Mock-Sicherungen lassen sich in die Echtdatenbank einspielen",
    "sicherung_identisch_neue_version": "M9: identischer Inhalt erzeugt trotzdem eine neue Version",
    "sicherung_probelauf_schreibt": "M9: der Probelauf spielt die Sicherung doch ein",
    "sicherung_ohne_bestaetigung": "M9: Einspielen ohne bestaetigt=true",
    "sicherung_tan_ignoriert": "M9: Einspielen trotz auf TAN wartendem Lauf",
    "sicherung_undo_ohne_sync": "M9: Rückgängig des Einspielens stellt den Bankkonto-Zustand nicht her",
    "sicherung_kennungen_nur_vorhandene": "M9: nur Kennungen existierender Buchungen werden gesichert",
    "sicherung_ohne_entscheidung": "M9: gespeicherte Entscheidungen je Bankkonto fehlen in der Sicherung",
    "sicherung_zaehler_ohne_vorlage": "M9: der ID-Zähler der Vorlagen wird nicht gesichert",
    "sicherung_vorschlag_ohne_sicherheit": "M9: die Sicherheit von Lernmodell-Vorschlägen geht verloren",
    # Meilenstein 4: GnuCash-Import
    "gnc_zweck_aus_beschreibung": "M4: Verwendungszweck aus der Beschreibung statt aus der Notiz",
    "gnc_versteckt_ignoriert": "M4: versteckte GnuCash-Konten werden nicht geschlossen",
    "gnc_iban_ohne_pruefsumme": "M4: IBAN aus der Kontonummer ohne Prüfsummenprüfung",
    "gnc_vorlagenbaum": "M4: Konten und Buchungen des SQLite-Vorlagenbaums werden importiert",
    "gnc_ohne_dubletten": "M4: GnuCash-Import ohne Dublettenerkennung",
    "kmy_ohne_gnc": "M4: KMyMoney-Import ordnet Konten mit gnc:-Kennung nicht zu",
    # Meilenstein 4: Lernmodell
    "lern_ohne_betrag": "M4: Lernmodell ohne Betragsmerkmal",
    "lern_vorschlaege_trainieren": "M4: offene Vorschläge zählen zur Trainingsmenge",
    "lern_nur_betrag": "M4: Vorhersage auch, wenn nur das Betragsmerkmal bekannt ist",
    "lern_ohne_glaettung": "M4: Naive Bayes ohne Laplace-Glättung",
    "lern_schwelle_halb": "M4: Schwelle 1/2 statt 7/10",
    "lern_bei_eigener_iban": "M4: Lernmodell auch bei eigener Gegen-IBAN (mögliche Umbuchung)",
    # Meilenstein 4: Split-Vorlagen
    "vorlage_toleranz": "M4: Abweichung um 1 Cent wird toleriert",
    "vorlage_inaktiv_greift": "M4: inaktive Vorlagen werden angewendet",
    "vorlage_nur_erste": "M4: nur die erste passende Vorlage wird im Betrag verglichen",
    "vorlage_ohne_memo": "M4: Teile verlieren ihr Memo",
    "vorlage_ohne_empfaenger": "M4: Vorlagen ohne Empfänger-Bedingung werden angenommen",
    "vorlage_nicht_angewendet": "M4: Treffer werden bei der Synchronisation nicht aufgeteilt",
    "vorlage_ohne_benachrichtigung": "M4: Abweichungen lösen keine Benachrichtigung aus",
    "vorlage_abweichung_mit_regel": "M4: bei Abweichung greifen Regeln, Standardkategorie und Lernmodell",
    "vorlage_protokoll_fehlt": "M4: Anwenden von Vorlagen wird nicht protokolliert",
    "beitragsaenderung_ignoriert": "M4: das Szenario beitragsaenderung liefert die normalen Beträge",
    # Meilenstein 5: Kredite (kredite.md)
    "kredit_30_360_tatsaechliche_tage": "M5: 30/360 zählt Perioden mit tatsächlichen Tagen",
    "kredit_act365_schaltjahr": "M5: act/365 rechnet im Schaltjahr mit Basis 366",
    "kredit_rundung_abschneiden": "M5: Zinsanteil abgeschnitten statt kaufmännisch gerundet",
    "kredit_sondertilgung_periodenende": "M5: Sondertilgung mindert den Zins erst ab der nächsten Periode",
    "kredit_sondertilgung_unbegrenzt": "M5: Sondertilgung über die Restschuld hinaus wird nicht begrenzt",
    "kredit_monatsende_verkettet": "M5: Fälligkeiten verkettet statt an der ersten verankert (31. → 29. → 29.)",
    "kredit_status_bestaetigt": "M5: aufgeteilte Raten erhalten den Status bestaetigt statt vorlaeufig",
    "kredit_toleranz_null": "M5: Raten werden nur am Fälligkeitstag selbst erkannt",
    "kredit_sync_nicht_aufgeteilt": "M5: Raten werden bei der Synchronisation nicht aufgeteilt",
    "kredit_korrektur_zwei_buchungen": "M5: Jahresabgleich erzeugt je Differenz eine eigene Korrekturbuchung",
    "kredit_abgleich_ohne_status": "M5: Jahresabgleich markiert die Raten nicht als abgeglichen",
    "kredit_abgleich_gegen_plan": "M5: Jahresabgleich vergleicht mit dem Plan statt mit der gebuchten Restschuld",
    "kredit_loeschen_zuordnung_bleibt": "M5: Löschen einer Rate lässt die Zuordnung im Kredit stehen",
    "kredit_konto_loeschbar": "M5: Konten mit Kreditbezug lassen sich löschen",
    "kredit_protokoll_fehlt": "M5: Kreditoperationen werden nicht protokolliert",
    "kredit_sicherung_fehlt": "M5: Kredite fehlen in der Sicherung",
    "kredit_sicherung_immer_schluessel": "M5: anzahl enthält kredit auch ohne Kredite (bricht M9-Prüfsummen)",
    # Meilenstein 5: wiederkehrende Buchungen (wiederkehrend.md)
    "wieder_ohne_toleranz": "M5: Kette ohne Toleranz für Wochenend-/Feiertagsverschiebung",
    "wieder_jahreskosten_monatlich": "M5: Jahreskosten immer Betrag × 12",
    "wieder_kette_mit_luecke": "M5: eine ausgelassene Zahlung beendet die Kette nicht",
    "wieder_ausbleibend_ohne_toleranz": "M5: ausbleibend schon am Tag nach der Fälligkeit",
    "wieder_neuer_empfaenger_einnahme": "M5: neuer Empfänger auch bei Einnahmen gemeldet",
    "wieder_entprellung_ungelesen": "M5: gelesene Ereignisse werden erneut gemeldet",
    "wieder_erstabruf_meldet": "M5: der Erstabruf eines Kontos meldet unerwartete Buchungen",
    # Meilenstein 5: Berichte und Export (berichte.md)
    "bericht_stichtag_exklusiv": "M5: Kontostand am Stichtag ohne die Buchungen des Tages",
    "bericht_umbuchung_als_ausgabe": "M5: Einnahmen/Ausgaben aus Bestandskonten (Umbuchungen zählen mit)",
    "bericht_ohne_unterkonten": "M5: unterkonten=true wird ignoriert",
    "csv_betrag_punkt": "M5: CSV-Betrag mit Dezimalpunkt",
    "csv_nur_erster_split": "M5: CSV exportiert nur den ersten Split jeder Buchung",
    "csv_ohne_bom": "M5: CSV ohne UTF-8-BOM",
    # Meilenstein 6: FinTS (fints.md)
    "fints_tan_im_log": "M6: python-fints protokolliert Nachrichten mit TAN auf DEBUG",
    "mt940_jahr_ohne_korrektur": "M6: MT940-Buchungstag ohne Jahreskorrektur am Jahreswechsel",
    "mt940_storno_vorzeichen": "M6: MT940 RC (Storno einer Gutschrift) positiv statt negativ",
    "camt_gegenpartei_ohne_storno": "M6: camt-Gegenpartei bei Storno nicht von der Gegenseite",
    "camt_nur_erster_ustrd": "M6: camt-Verwendungszweck nur aus dem ersten Ustrd",
    "fints_tan_ungueltig_leer": "M6: falsche TAN liefert eine leere Umsatzliste statt TanUngueltig",
    "fints_ohne_referenz": "M6: camt-Bankreferenz ignoriert (immer Hash-Kennung)",
    "fints_hash_ohne_nummer": "M6: Hash-Kennung ohne laufende Nummer (gleiche Umsätze verschmelzen)",
    # Meilenstein 6: IMAP und Mail (mail.md)
    "imap_anhang_als_text": "M6: text/plain-Anhang wird als Nachrichtentext genommen",
    "imap_ohne_erneuern": "M6: abgelehntes Access-Token wird nicht erneuert",
    "imap_select_statt_examine": "M6: Ordner mit SELECT statt EXAMINE geöffnet",
    "imap_ohne_peek": "M6: Inhalte mit BODY[] statt BODY.PEEK[] geholt",
    "mail_nacheinander": "M6: Postfächer nacheinander statt parallel abgerufen",
    "mail_filter_ignoriert": "M6: Absenderfilter wird nicht angewendet",
    "oauth_ohne_pkce": "M6: code_challenge ohne SHA-256 (plain)",
    "oauth_ablauf_ignoriert": "M6: abgelaufener Refresh-Token wird nicht proaktiv erkannt",
    "vorwarnung_jeder_takt": "M6: Vorwarnung zum Token-Ablauf in jedem Takt (Flut)",
    "oauth_widerruf_als_ablauf": "M6: Widerruf wird als Ablauf gemeldet",
    "oauth_ablauf_feld_ignoriert": "M6: refresh_token_expires_in der Tokenantwort ignoriert",
    "postfach_sicherung_fehlt": "M6: Postfächer fehlen in der Sicherung",
    "postfach_sicherung_immer_schluessel": "M6: anzahl enthält postfach auch ohne Postfächer",
    # Meilenstein 6: PIN, Geheimnisse, Zustellung, Erinnerungen
    "pin_systemd_nicht_gesperrt": "M6: falsche PIN aus systemd-creds wird erneut verwendet",
    "geheimnis_klartext": "M6: Geheimnis im Klartext in der Datenbankdatei",
    "zustellung_doppelt": "M6: zugestellte Benachrichtigungen werden erneut gesendet",
    "zustellung_ohne_grenze": "M6: nach der Höchstzahl der Versuche wird weiter zugestellt",
    "zustellung_ohne_wiederholung": "M6: fehlgeschlagene Zustellungen werden im Planer nicht wiederholt",
    "ntfy_ohne_mock_praefix": "M6: Push-Nachrichten im Mock-Modus ohne [Mock] im Titel",
    "tan_erinnerung_nach_antwort": "M6: Erinnerungen auch nach Beantwortung oder Abbruch",
    "tan_erinnerung_ohne_grenze": "M6: mehr Erinnerungen als tan_erinnerung_anzahl",
    "tan_erinnerung_nachholen": "M6: ausgelassene Erinnerungen werden nachgeholt",
    # Meilenstein 7: Anmeldung, Härtung, Betrieb (sicherheit.md, betrieb.md)
    "m7_hash_ohne_nfc": "M7: Passwort ohne NFC-Normalisierung gehasht",
    "m7_hash_parameter_fest": "M7: Prüfen ignoriert die gespeicherten scrypt-Parameter",
    "m7_passwortlaenge_roh": "M7: Passwortlänge vor statt nach NFC gezählt",
    "m7_oeffentlich_konten": "M7: GET /api/konten ohne Anmeldung erreichbar",
    "m7_401_nach_404": "M7: unbekannte Pfade ohne Sitzung liefern 404 statt 401",
    "m7_csrf_ungeprueft": "M7: CSRF-Token wird nicht geprüft",
    "m7_herkunft_ungeprueft": "M7: Origin/Sec-Fetch-Site werden nicht geprüft",
    "m7_sperre_prueft_passwort": "M7: während der Sperre wird das richtige Passwort angenommen",
    "m7_sperre_ohne_verdopplung": "M7: Sperrdauer verdoppelt sich nicht",
    "m7_leerlauf_ignoriert": "M7: Sitzungen laufen im Leerlauf nicht ab",
    "m7_hoechstdauer_ignoriert": "M7: Sitzungen haben keine Höchstdauer",
    "m7_abmelden_nur_cookie": "M7: Abmelden löscht nur das Cookie, die Sitzung bleibt gültig",
    "m7_passwortaenderung_sitzungen_bleiben": "M7: Passwortänderung beendet andere Sitzungen nicht",
    "m7_cookie_ohne_httponly": "M7: Sitzungs-Cookie ohne HttpOnly",
    "m7_ohne_nosniff": "M7: X-Content-Type-Options fehlt",
    "m7_csp_inline": "M7: CSP erlaubt Inline-Skripte",
    "m7_upload_grenze_exklusiv": "M7: genau upload_max_mib wird schon abgelehnt",
    "m7_anfrage_grenze_ignoriert": "M7: anfrage_max_kib wird nicht durchgesetzt",
    "m7_netz_ignoriert": "M7: erlaubte_netze wird nicht durchgesetzt",
    "m7_netz_xff": "M7: X-Forwarded-For bestimmt die Client-Adresse",
    "m7_sicherung_mit_hash": "M7: der Passwort-Hash steht in der Sicherung",
    "m7_aufbewahrung_alle_modi": "M7: Aufbewahrung löscht auch Sicherungen des anderen Modus",
    "m7_aufbewahrung_aelteste": "M7: Aufbewahrung behält die ältesten statt der neuesten Sicherungen",
    # Meilenstein 8: Test-Benachrichtigung (W-005, benachrichtigungen.md 8)
    "m8_test_in_mock_liste": "M8: Test-Benachrichtigung landet beim Mock-Plugin in /api/mock/zustellungen",
    # Meilenstein 8: Oberfläche (oberflaeche.md, Wegwerf-Seite referenz/kontor/oberflaeche/, E-149)
    "m8_strg_ersetzt": "M8: Strg+Klick ersetzt die Auswahl, statt die Zeile umzuschalten",
    "m8_umschalt_ohne_anker": "M8: Umschalt+Klick wählt ab der ersten Zeile statt ab dem Anker",
    "m8_kontextmenue_ohne_auswahl": "M8: Rechtsklick außerhalb der Auswahl lässt die alte Auswahl stehen",
    "m8_palette_ohne_umlaute": "M8: Befehlspalette ohne Umlautfaltung (ü ≠ ue)",
    "m8_mehrfach_nur_erste": "M8: Mehrfachbearbeitung sendet nur die erste ausgewählte Buchung",
    "m8_mock_hinweis_mobil": "M8: Mock-Hinweis im mobilen Layout ausgeblendet",
    "m8_huelle_inline_skript": "M8: die Hülle enthält ein Inline-Skript",
    "m8_esc_ohne_fokus": "M8: Esc schließt das Kontextmenü, gibt den Fokus aber nicht zurück",
    "m8_fehler_ohne_servermeldung": "M8: Ablehnung beim Kategorie setzen ohne die meldung des Servers (W-007)",
    # Meilenstein 11: Kontostand, Kategorien als Konten, Empfänger zusammenführen
    "saldo_mit_vormerkungen": "M11: Mock-Saldo enthält Vormerkungen",
    "saldo_ohne_stichtag": "M11: Kontor-Saldo ohne Stichtag der Bank (spätere Buchungen zählen mit)",
    "saldo_vorzeichen": "M11: Ausgleichsbuchung mit umgekehrtem Vorzeichen",
    "saldo_kein_ausgleich": "M11: Differenz wird gemeldet, aber nicht gebucht",
    "saldo_kennung_doppelt": "M11: zweite Ausgleichsbuchung am selben Tag mit derselben Kennung",
    "unterkonten_ignoriert": "M11: Filter unterkonten ohne Wirkung",
    "unterkonten_betrag_nur_konto": "M11: Betrag mit unterkonten nur aus dem Konto selbst",
    "zusammenfuehren_name_ignoriert": "M11: Zusammenführen ignoriert den neuen Namen",
    "zusammenfuehren_alter_name_fehlt": "M11: alter Name des Ziels wird beim Umbenennen kein Alias",
    "fints_saldo_ohne_vorzeichen": "M11: FinTS-Saldo ohne Soll/Haben-Kennzeichen",
    "m11_unterkonten_ignoriert": "M11: Oberfläche schickt unterkonten nicht mit",
    "m11_konto_erstes": "M11: Spalte Konto zeigt bei mehreren Bestandskonten das erste",
    "m11_kategorien_anfangs_offen": "M11: Kategorien der Übersicht anfangs aufgeklappt",
    "m11_zusammenfuehren_ohne_name": "M11: Dialog schickt den neuen Namen nicht mit",
    # Meilenstein 12: Statusänderung, Massenänderungen, Filterleiste
    "m12_alte_uebergaenge": "M12: mehrfach/aendern erzwingt die alten Statusübergänge",
    "m12_entsperren_ignoriert": "M12: abgeglichene Buchungen verlassen ihren Status ohne entsperren",
    "m12_sperre_ignoriert": "M12: Datum, Empfänger und Verwendungszweck gesperrter Buchungen änderbar",
    "m12_nicht_atomar": "M12: Massenänderung ändert freie Buchungen, bevor sie die Sperre meldet",
    "m12_vorschlag_bleibt": "M12: Status bestätigt lässt den offenen Vorschlag stehen",
    "m12_abgestimmt_status_gesperrt": "M12: Status abgestimmter Buchungen ist gesperrt",
    "m12_filter_offen": "M12: Filterleiste auf dem Desktop anfangs eingeblendet",
    "m12_ohne_rueckfrage": "M12: Verlassen von abgeglichen ohne Rückfrage (entsperren sofort)",
    "m12_mehrfach_status_nur_erste": "M12: Status der Auswahl wird nur für die erste Buchung gesetzt",
    "m12_status_per_patch": "M12: Inline-Status über PATCH (alte Übergänge) statt mehrfach/aendern",
    # Meilenstein 13
    "m13_version_normalisiert": "M13: Version in PEP-440-Normalform (0.7 statt 0.07)",
    "m13_huelle_ohne_version": "M13: Versionsanzeige fehlt in der ausgelieferten Hülle",
    "m13_feld_fehlt": "M13: GET /api/version ohne sicherung_schema",
    "m13_entwicklungsstand_falsch": "M13: entwicklungsstand false, obwohl commit und build_datum null sind",
    "m13_datenbank_relativ": "M13: datenbank als konfigurierter (relativer) statt absoluter Pfad",
    "m13_version_oeffentlich": "M13: GET /api/version auch ohne Anmeldung erreichbar",
    "m13_navigation_erweitert": "M13: zusätzlicher Navigationseintrag nav-ueber",
    "m13_knopf_zuerst": "M13: version-knopf am Anfang statt als letztes Element der Navigation",
    "m13_fokus_mobil_falsch": "M13: mobil Fokus nach dem Schließen auf den verborgenen version-knopf",
    "m13_ohne_neuladen": "M13: Versionsangaben beim Start geladen, Fehlschlag beim Öffnen unbemerkt",
    # Meilenstein 15: Sammelpaket Bedienung (referenz/kontor/m15.py, m3.py, m2.py)
    "m15_bis_ohne_bis_id": "M15: Rückgängig bis nimmt die Änderung bis_id selbst nicht mit zurück",
    "m15_bis_ohne_paare": "M15: Rückgängig bis nimmt nur anfangs wirksame Änderungen zurück (ohne Paare)",
    "m15_bis_leer_200": "M15: Rückgängig bis ohne Nettowirkung legt eine leere Änderung an (E-190)",
    "m15_loeschen_nicht_atomar": "M15: mehrfach/loeschen löscht freie Buchungen, bevor es die Sperre meldet",
    "m15_verschieben_reihenfolge": "M15: Verschieben prüft die Sperre vor verschieben_unmoeglich",
    "m15_verschieben_neue_split_id": "M15: verschobene Splits erhalten eine neue ID",
    "m15_herkunft_geloeschte": "M15: Herkunft zählt auch gelöschte Buchungen",
    "m15_sync_legt_an": "M15: sync_konten_anlegen = False legt unbekannte Bankkonten trotzdem an",
    "m15_zuordnung_ungelesen": "M15: Zuordnung per PATCH/POST lässt die Benachrichtigung ungelesen",
    "m16_ohne_ueberspringen": "M16: alte Kette – jede zusätzliche Zahlung beendet die Kette",
    "m16_anker_juengster": "M16: Anker ist immer der jüngste Eintrag",
    "m16_anker_ohne_betrag": "M16: Anker-Auswahl ohne die Regel „gleicher Betrag wie der Vorgänger“",
    "m16_vorgaenger_ohne_betrag": "M16: Vorgänger nur nach kleinster Abweichung, ohne Vorrang des gleichen Betrags",
    "m16_ohne_vorige_kandidaten": "M16: Vorgänger-Kandidaten des vorigen Schritts gelten nicht als zusätzlich",
    "m16_zusaetzlich_nur_nahe_c": "M16: zusätzlich nur, was höchstens T Tage vom aktuellen Glied entfernt ist",
    "m16_abweichung_ohne_vorzeichen": "M16: abweichung_tage ohne Vorzeichen",
    "m16_ohne_ankerschritt": "M16: Kettenprotokoll ohne Schritt anker bei mehreren Kandidaten",
    "m16_stichtag_ignoriert": "M16: Begründung berücksichtigt Buchungen nach dem Stichtag",
    "m16_vor_beginn_als_keine_serie": "M16: Einträge vor dem ersten Glied erhalten die Rolle keine_serie",
    "m16_buchungen_aelteste_zuerst": "M16: Buchungen der Gruppe älteste zuerst",
    "m16_urteil_zusaetzlich_als_nicht": "M16: Gesamturteil nicht_wiederkehrend statt zusaetzlich",
    "m16_unbekannter_parameter_erlaubt": "M16: Begründung nimmt unbekannte Query-Parameter an",
    # Meilenstein 25 (Betragsfilter, wiederkehrend.md 9)
    "m25_schwelle_exklusiv": "M25: Mindestschwelle schließt den Grenzbetrag aus",
    "m25_nie_streng": "M25: übergangene jüngere Einträge machen die Kette nicht streng",
    "m25_vorgaenger_ohne_toleranz": "M25: Vorgängerwahl ohne die Stufe „Betrag passt“",
    "m25_dazwischen_bricht": "M25: nicht passende Einträge zwischen zwei Gliedern brechen die Kette",
    "m25_ohne_betragsbruch": "M25: kein Bruch mit Grund betrag, Preisänderung immer verbunden",
    "m25_anker_wie_m16": "M25: Anker-Kandidaten bei Toleranz wie M16 (nur T Tage vor dem jüngsten)",
    "m25_ohne_mehrheitsregel": "M25: Mehrheitsregel der Vorgabe fehlt",
    "m25_empfaenger_mit_feld": "M25: GET /api/empfaenger liefert das Feld wiederkehrend",
    "m25_vorgabe_schwelle_erlaubt": "M25: Vorgabe nimmt den Modus mindestschwelle an",
    "m25_meldung_unter_schwelle": "M25: geänderter Betrag wird auch unter der Mindestschwelle gemeldet",
    "m25_rolle_vor_beginn": "M25: übergangene Einträge haben die Rolle vor_beginn statt anderer_betrag",
    "m26_ohne_etag": "M26: Dateien unter /oeffentlich/ ohne ETag",
    "m26_ohne_304": "M26: passendes If-None-Match liefert 200 statt 304",
    "m26_cache_frei": "M26: Dateien unter /oeffentlich/ mit max-age statt no-cache",
    "m32_kontonamen_doppelt": "M32-Nachzug (M1/M3): gleichnamige Konten auf derselben Ebene erlaubt, nichts bereinigt",
    "m32_standardkategorie_bleibt": "M3: Standardkategorie wird weiter angenommen (ab M32 nur noch null, E-308)",
    "m28_alt_acht": "M28: Alt+1 … Alt+8 nach der alten Navigation (Kredite auf Alt+5)",
    "m28_palette_alt": "M28: „Gehe zu“-Einträge der Befehlspalette in Navigationsreihenfolge",
    "m28_stift_ohne_status": "M28: Status nur per Doppelklick in der Zeile, kein Stift in den Einzelheiten",
}

ZUSAMMENFASSUNG = re.compile(r"=+ (.*?) in [0-9.]+s")

#: Meilensteine, deren Kern-Tests keine Referenz haben und hier nicht laufen (E-225, E-243, E-256, E-266); Abnahme nur gegen die App
OHNE_REFERENZ = ("m18", "m19", "m20", "m23", "m24", "m27", "m29", "m30", "m31", "m32")
MARKER = "kern and not (" + " or ".join(OHNE_REFERENZ) + ")"


def bereich(mutant: str) -> list[str]:
    """Kern-Tests des Meilensteins, zu dem der Mutant gehört (Vorauswahl, siehe lauf)."""
    m = re.match(r"M([0-9]+):", MUTANTEN[mutant])
    if m is None:
        return sorted(str(p.relative_to(REPO)) for p in (REPO / "tests" / "app").glob("test_*.py"))
    return [f"tests/app/m{m[1]}"]


def lauf(mutant: str | None, *, alle: bool, zusatz: bool = False) -> tuple[int, str, float]:
    """Ein Lauf der Kern-Tests gegen die Referenz (mit Mutant).

    Ein Mutant gilt als erkannt, wenn mindestens ein Kern-Test rot wird. Um Zeit
    zu sparen, laufen zuerst nur die Kern-Tests seines Meilensteins (``-x``);
    bleiben sie grün, entscheidet der Lauf über alle Kern-Tests. Das Kriterium
    ist dasselbe, denn die Tests sind voneinander unabhängig.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REFERENZ), str(REPO)])
    env["KONTOR_MUTANT"] = mutant or ""
    env["KONTOR_TESTS_ZUSATZFELDER"] = "1" if zusatz else ""
    env.setdefault("HYPOTHESIS_PROFILE", "standard")
    env.pop("KONTOR_TESTS_OHNE_APP", None)
    rest = ["-m", MARKER, "-q", "-p", "no:cacheprovider", "--no-header", "-o", "addopts="]
    start = time.monotonic()
    r = None
    if mutant and not alle:
        r = subprocess.run([sys.executable, "-m", "pytest", *bereich(mutant), *rest, "-x"], cwd=REPO, env=env,
                           capture_output=True, text=True)
        if r.returncode != 1:
            r = None
    if r is None:
        befehl = [sys.executable, "-m", "pytest", "tests/app", *rest]
        if mutant and not alle:
            befehl.append("-x")
        r = subprocess.run(befehl, cwd=REPO, env=env, capture_output=True, text=True)
    dauer = time.monotonic() - start
    zeilen = [z for z in r.stdout.splitlines() if z.strip()]
    zusammenfassung = zeilen[-1].strip("= ") if zeilen else "(keine Ausgabe)"
    erster = next((z.split(" - ")[0].replace("FAILED ", "") for z in zeilen if z.startswith("FAILED")), "")
    if mutant and erster:
        zusammenfassung += f"; erster Fehlschlag: {erster}"
    if r.returncode not in (0, 1):
        zusammenfassung += f"; Rückgabecode {r.returncode}: {(r.stdout + r.stderr)[-1500:]}"
    return r.returncode, zusammenfassung, dauer


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--nur-referenz", action="store_true")
    p.add_argument("--ohne-erweiterung", action="store_true", help="Erweiterungslauf (E-124) auslassen")
    p.add_argument("--mutant", action="append", choices=sorted(MUTANTEN))
    p.add_argument("--alle-fehlschlaege", action="store_true", help="Mutantenläufe nicht beim ersten Fehler abbrechen")
    p.add_argument("--protokoll", type=Path, help="Ergebnis zusätzlich als Markdown schreiben")
    a = p.parse_args()

    zeilen = [f"# Selbstprüfung {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
              f"Python {sys.version.split()[0]}, HYPOTHESIS_PROFILE={os.environ.get('HYPOTHESIS_PROFILE', 'standard')}",
              "", "| Lauf | Erwartung | Ergebnis | Bewertung | Dauer |", "| --- | --- | --- | --- | --- |"]
    ok = True
    code, text, dauer = lauf(None, alle=True)
    gut = code == 0
    ok &= gut
    zeilen.append(f"| Referenz (ohne Mutant) | alle Kern-Tests grün | {text} | {'OK' if gut else 'FEHLER'} | {dauer:.0f} s |")
    print(zeilen[-1], flush=True)
    if not a.ohne_erweiterung:
        # Erweiterungslauf (E-124): jedes Antwortobjekt mit einem zusätzlichen optionalen Feld
        code, text, dauer = lauf(None, alle=True, zusatz=True)
        gut = code == 0
        ok &= gut
        zeilen.append(f"| Referenz mit Zusatzfeldern (E-124) | alle Kern-Tests grün | {text} | "
                      f"{'OK' if gut else 'FEHLER'} | {dauer:.0f} s |")
        print(zeilen[-1], flush=True)
    if not a.nur_referenz:
        for name in a.mutant or MUTANTEN:
            code, text, dauer = lauf(name, alle=a.alle_fehlschlaege)
            gut = code == 1
            ok &= gut
            zeilen.append(f"| Mutant `{name}`: {MUTANTEN[name]} | mindestens ein Test rot | {text} | "
                          f"{'OK (erkannt)' if gut else 'FEHLER (nicht erkannt)'} | {dauer:.0f} s |")
            print(zeilen[-1], flush=True)
    zeilen += ["", f"Gesamtergebnis: {'BESTANDEN' if ok else 'NICHT BESTANDEN'}", ""]
    if a.protokoll:
        a.protokoll.write_text("\n".join(zeilen), encoding="utf-8")
    print(zeilen[-2])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
