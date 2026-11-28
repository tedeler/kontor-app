# Geänderte Tests gegenüber legacy-tests

Jede Anpassung eines früheren Abnahmetests (`gesamt-tests/`) oder eines eigenen Tests wegen geänderten Verhaltens,
neueste unten. Bis 2026-11-28 stand diese Liste in `TESTUMBAU.md` im Wurzelverzeichnis (D-327).

Im Ausgangsstand schlugen 19 Tests der Abnahmesuite und 3 eigene fehl. Kein Anwendungscode wurde geändert.

| Test | Ursache | Änderung |
| --- | --- | --- |
| `m13/test_m13_oberflaeche` (2), `m8/test_m8_auslieferung` (1), `m8/test_m8_grundgeruest` (2), eigene `test_browser.py::test_ueber_fenster`, `test_versionierung_eigen.py::test_huelle_zeigt_version_in_der_navigation` | Auf einem Feature-Branch zeigt die App den Branch statt der Version; die Tests liefen nur auf main grün | Beide Suiten setzen den Branch für Tests außer Kraft (`_ohne_branch` bzw. `tests/conftest.py`) |
| `m8/test_m8_panels_mobil.py::test_wischen_links_setzt_kategorie_und_rueckgaengig` | D-290: Die Zeile zeigt die Kategorie sofort; das Attribut der Zeile ist kein Zeichen mehr dafür, dass neu geladen ist | wartet zusätzlich auf `data-ausstehend="0"` an `seite-konto`, bevor es mit den Zeilen weiterarbeitet |
| `test_buchungen.py::test_kategorie_setzen_fehler` | D-242: Bestandskonto ist als Ziel zulässig | erwartet `konto_ungueltig` für das eigene Konto, `kategorie_ungueltig` nur noch für Eigenkapital |
| `test_mehrfach.py::test_kategorie_ziel_ungueltig` (2 Varianten), `test_kategorie_pruefreihenfolge`, `test_mehrfach_kategorie_gegen_modell` | D-242 | Bestandskonten als ungültiges Ziel entfernt bzw. durch Eigenkapital ersetzt |
| `test_plugins.py::test_nur_lesende_oeffentliche_methoden` (2), `m6/test_m6_paket.py::test_oeffentliche_methoden` | D-243: Mail-Plugin hat `koepfe` und `inhalte` | erwartete Methodenmenge ergänzt |
| `m8/test_m8_seiten.py::test_seiten_im_mindestumfang` | Ohne Treffer zeigt „Regeln anwenden“ nur die Erfolgsmeldung, die ausgeliefert aus ist | Seite mit eingeschalteter Erfolgsmeldung |
| `m8/test_m8_split_dnd.py::test_umbuchung_auf_kategorie_ziehen_aendert_nichts` | D-242: Eine Umbuchung lässt sich jetzt zuordnen; die Aussage des Tests gilt nicht mehr | Test entfernt |
| `test_browser_nachweis_pdf.py::test_v_p_und_kontextmenue` | D-311: Im Kontoblatt einer Kategorie gibt es den Nachweis jetzt | prüft statt des fehlenden Eintrags den Buchungsnachweis der Kategorie |
| `test_nachweis_pdf_eigen.py::test_fehler` | D-311: Der Nachweis geht auch aus dem Kontoblatt einer Kategorie | Kategorie mit fremder Buchung erwartet `buchung_nicht_im_konto`, `kein_bestandskonto` nur noch für „Unkategorisiert“; Angaben einer Kategorie 200 |
| `m8/test_m8_tastatur.py::test_alt_ziffern_und_schraegstrich`, `::test_suche_und_tastaturhilfe`, `m28/test_m28_kontoblatt.py::test_kuerzel_aktionen_und_vortasten` | D-292: `/` entfällt, die Hilfe liegt auf `h` | Suche über `w s`, Hilfe über `h` |
| `m28/test_m28_kontoblatt.py::test_filter_untermenue` (4 Varianten) | D-292: Untermenü „Filter“ hat zwei Einträge für den Betrag | erwartete Liste der Einträge ergänzt |
| eigene `test_browser_tastatur.py` (2 Tests) | D-292: `v d` entfällt, `f w` ist „diese Woche“, Hilfe auf `h`, F6 mit „Aktionen“ | Panel über den Knopf eingeklappt, Erwartungen nachgezogen |
| `m28/test_m28_kontoblatt.py::test_kuerzel_aktionen_und_vortasten` | Prüfte den Fokus ohne zu warten; schlug in 4 von 6 Läufen fehl (auch in legacy-tests) | wartet auf den Fokus |
| `m8/test_m8_auslieferung.py::test_manifest` | D-286: Im Mock-Modus heißt die Anwendung im Manifest „Kontor Test“ (eigene Symbole unter denselben Adressen) | erwartet `name` und `short_name` „Kontor Test“; die übrigen Prüfungen (Größen, `maskable`, Farben) unverändert |
| `m30/test_m30_oberflaeche.py::test_regelliste` | Tastendruck auf einen Griff, den die Seite gerade neu aufbaut; schlug gelegentlich fehl | drückt erneut, solange die Reihenfolge unverändert ist |
| `m15/test_m15_oberflaeche.py::test_details_vorschlag_und_kandidaten`, `m8/test_m8_kontextmenue.py::test_kategorie_setzen_umbuchung_meldet_ablehnung`, `m8/test_m8_kontoansicht.py::test_liste_gleich_rest_und_darstellung` (2) | schlagen fehl (die letzten drei wegen D-242, der erste nicht untersucht) | nicht angepasst; stehen in `abgewaehlt.txt` und schlagen mit `--alle` weiter fehl |
| eigene `test_browser_ausdruck.py::test_tags_im_kontoblatt_bearbeiten` | schlug einmal in vier Läufen fehl, danach nicht mehr | unverändert; beobachten |
| eigene `test_browser_spalten.py::test_markierung_der_zeilen`, `m22/test_m22_oberflaeche.py::test_markierung_rangfolge_und_darstellung` (abgewählt) | D-254: Zeilenfarbe folgt nur dem Status, `kategorisiert` entfällt | erwartet `vorlaeufig`/`bestaetigt`; Unterscheidbarkeit an importiert, vorläufig, bestätigt; „folgt Änderungen“ über Statuswechsel statt Kategorie |
| `test_buchungen.py`, `test_invarianten.py` (Tabelle `UEBERGAENGE`), `m28/test_m28_kontoblatt.py::test_bestaetigen_vorlaeufig_bleibt_und_zuruecknehmen` (abgewählt) | D-257: `vorlaeufig → bestaetigt` ist zulässig; Bestätigen erfasst auch vorläufige Buchungen | Übergang in die Tabelle aufgenommen; erwartet nach dem Bestätigen `bestaetigt` (nicht ausgeführt, nur nach Lektüre angepasst) |
| eigene `test_browser_sammel3.py` (2 Tests), `m28/test_m28_kontoblatt.py`, `m28/test_m28_seiten.py`, `m32/test_m32_oberflaeche.py` | D-262: Das Bestätigungs-Tag heißt „<Name>-Bestätigt“ statt „B-<Name>“ | erwarteter Tag-Name ersetzt (nicht ausgeführt, nur nach Lektüre angepasst) |
| `m2/test_m2_vorschlag.py` (3 Tests), `m3/test_m3_abstimmung.py::test_sperre_abgestimmter_buchungen`, `m4/test_m4_vorlagen_sync.py` (2 Tests) | D-261: Vorschlag und Split-Vorlage machen `vorlaeufig`, Annehmen `bestaetigt`, Ablehnen wieder `importiert` | erwarteter Status angepasst |
| `test_buchungen.py::test_kategorie_setzen`, `test_mehrfach.py::test_kategorie_genau_die_markierten`, `m12/test_m12_rest.py::test_abgeglichen_verlassen_braucht_entsperren` | D-261: Zuordnung von Hand (Kategorie, Splits) macht `bestaetigt` | erwarteter Status angepasst |
| `m30/test_m30_ausdruck.py::test_sprache_felder` (Hilfe `m30.FELDER`), `spec/test_openapi.py::test_m5_schemas` | D-263: Filterfeld `verdächtig`; D-271: `position_id` gehört nur zur Buchungsliste, nicht zum Export | Feld bzw. Ausnahme ergänzt |
| `m30/test_m30_ausdruck.py::test_sprache_felder` (Hilfe `m30.FELDER`) | D-297: Filterfeld `unbestätigt` | Feld ergänzt |
| eigene `test_browser.py::test_panels_und_layout` | D-265, D-266: kein Panel Kategorien; Einzelheiten rechts oder unten | prüft Breite und Andocken der Einzelheiten |
| `m28/test_m28_kontoblatt.py::test_filter_untermenue`, `m8/test_m8_panels_mobil.py::test_groesse_per_tastatur`, `::test_mobil_kein_andocken_layout_bleibt` | D-271: Filterwechsel behält die Auswahl; D-265: kein Panel Kategorien | Auswahl = gewählte Buchung; Griff und Andocken der Einzelheiten statt des Panels Kategorien |
| eigene `test_browser_ausdruck.py::test_tags_im_kontoblatt_bearbeiten` | öffnete den Tag-Dialog, bevor die Liste neu geladen war; erneut rot im CI-Lauf vom 2026-11-24 | wartet, bis die Zeile das neue Tag zeigt (D-274) |
| `m8/test_m8_split_dnd.py::test_split_bearbeiten` | D-272: Splits speichern setzt bei gewählter Person auch deren Tag (weitere Änderungen im Protokoll) | zählt nur die Änderung der Splits; die Tag-Änderungen sind zugelassen |
| `m26/test_m26_oberflaeche.py::test_erfassen_schwebend_und_titelzeile` | D-283: `buchung-erfassen` ist mobil ausgeblendet | prüft, dass der Knopf vorhanden, aber nicht sichtbar ist |
| eigene `test_browser.py::test_bericht_sprung_mobil_mit_nachladen_nicht_verdeckt`; `m26/test_m26_oberflaeche.py::test_suchtreffer_kompakt_und_tippen_springt` | D-281: mobil wählt der Sprung zu einer Buchung nichts mehr aus | Ziel ist markiert (`data-markiert`) und fokussiert, Auswahl leer |
| eigene `test_browser.py::test_mobil`; `m26/test_m26_oberflaeche.py::test_zurueck_beendet_auswahl_ohne_ansicht_zu_verlassen`, `::test_kontextmenue_als_blatt`; `m8/test_m8_panels_mobil.py::test_wischen_links_setzt_kategorie_und_rueckgaengig`; `m18/test_m18_oberflaeche.py::test_mobil_marke_und_kamera` | D-278: mobil markiert Tippen nur, Doppeltipp öffnet die Einzelheiten, lange Berührung öffnet das Kontextmenü, Wischen nach rechts bestätigt | Auswahlmodus über `km-auswahl` (Hilfen `m8.auswahl_starten_mobil`, `m8.doppeltipp`), weitere Zeilen durch Tippen |
| `m26/test_m26_oberflaeche.py::test_kopfzeile_eine_zeile_reihenfolge_und_groesse` | D-279: „Wiederholen“ fehlt unter 403 px, die Kopfzeile ist wieder einzeilig | `m26.KOPF` ohne `wiederholen-knopf`; „eine Zeile“ wird wieder geprüft |
| eigene `test_mail_fortschritt_eigen.py::test_hintergrund_mit_fortschritt`, `test_oberflaeche.py::test_oberflaeche_nutzt_nur_spezifizierte_api` | D-284: `GET /api/mail/abruf/stand` nennt zusätzlich `automatisch` und `intervall_minuten`; neuer Pfad `GET /api/bestand/stand` | erwarteter Stand um die zwei Felder ergänzt; Pfad in `REST` aufgenommen |
| abgewählte Tests zu 36.3.1/36.3.2/36.4.1 (`m26`: lange Berührung wählt aus, Wischen rechts wählt; `m8/test_m8_panels_mobil.py`: Wischen rechts) | D-278 löst diese Festlegungen ab | nicht angepasst (abgewählt); vor einem Wiederaufnehmen in `abgewaehlt.txt` nach `oberflaeche.md` 43 umschreiben |
| `spec/test_openapi.py::test_alle_operationen_vorhanden`, eigene `test_oberflaeche.py::test_oberflaeche_nutzt_nur_spezifizierte_api` | D-280: drei neue Operationen unter `/api/saldoausgleich/paare` | erwartete Operationen bzw. Pfade ergänzt |
| `spec/test_openapi.py::test_alle_operationen_vorhanden` | D-295: neue Operation `POST /api/regeln/{regel_id}/uebernehmen` | in `OPERATIONEN_M30` ergänzt |
| eigene `test_oberflaeche.py::test_oberflaeche_nutzt_nur_spezifizierte_api` | D-303: neuer Pfad `/api/export/nachweis` (Nachweis als PDF) | Pfad ergänzt |

Stabilität: Nach den Änderungen lief der Browser-Teil der Gesamtsuite viermal hintereinander grün.
| eigene `test_m6_eigen.py::test_sicherung_der_schemaversion_2_einspielbar_und_postfach_bleibt_erhalten`, `test_geplant_eigen.py::test_sicherung_und_altbestand` | D-302: Sicherungsdatei Schemaversion 11 (Einstellungen) | erwartete Schemaversion 11 bzw. mindestens 10 |
| eigene `test_browser_einstellungen.py::test_suche_und_erweitert` | D-302: neuer Eintrag „Sicherungspunkte“ im Bereich Daten (Synonym „backup“) | drei statt zwei Treffer für „backup“ |
| `m31/test_m31_lernmodell.py::test_einstellungen_nicht_in_der_sicherung`, `m25/test_m25_rest.py::test_sicherung_rundreise` | D-302: Einstellungen der Instanz (Lernschwelle, automatische Regeln, Vorgabe des Betragsfilters) gehören ab Schemaversion 11 zur Sicherung und kommen beim Einspielen mit; die Inhaltsprüfsumme bleibt ohne sie | erwarten die Einstellungen der Quelle statt der des Ziels |
| `spec/test_openapi.py::test_alle_operationen_vorhanden` | D-302: sieben neue Operationen unter `/api/sicherung/punkte` | in `OPERATIONEN_M9` ergänzt |
| `m7/test_m7_betrieb.py::test_sicherung_service_und_timer` | D-302: Die zeitgesteuerte Sicherung legt stündlich Sicherungspunkte an (`sicherungspunkte.md` 8) | `ExecStart` mit `stunde --verzeichnis /var/lib/kontor/sicherungen`, `OnCalendar=hourly` |
| `app/m8/test_m8_kontoansicht.py::test_vorschlaege_annehmen_und_ablehnen` | D-305: Knöpfe ✓/✗ in der Zeile entfallen | Desktop über das Kontextmenü (`km-vorschlag-annehmen`/`-ablehnen`); Handy: Annehmen durch Wischen nach rechts, Ablehnen über die Schnittstelle (der Weg über Kontextmenü/Einzelheiten ist anderswo geprüft); Prüfung „Klick ändert die Auswahl nicht“ entfällt mit den Knöpfen |
| `app/m15/test_m15_oberflaeche.py` (Vorschlagsmarken) | D-305 | statt „Knöpfe mobil sichtbar“ nun „keine Knöpfe“ (Desktop und Handy) |
| eigene `test_browser_vorschlag_sofort.py` | D-305 | Entscheidung über Zeile markieren und `a`/`A` statt Knopf |
| eigene `test_browser_buchung_teilen.py` | D-306: neue Gestaltung des Teilen-Texts | erwarteter Text in neuer Form; Fall Kategorieansicht ergänzt |
| `m31/test_m31_regeln_automatisch.py::test_loeschen_sperrt_den_empfaenger_rueckgaengig_hebt_auf` → `test_loeschen_sperrt_nicht_rueckgaengig_bringt_zurueck`, neu `test_deaktivierte_regel_verhindert_neue`; `test_sicherung_rundreise` | D-308: Das Löschen einer automatischen Regel sperrt den Empfänger nicht mehr; eine deaktivierte Regel verhindert eine neue | Löschen ohne Eintrag `empfaenger`, Regel entsteht wieder; Rundreise mit deaktivierter Regel statt Sperre |
| `m30/test_m30_oberflaeche.py::test_regelliste` | D-308: deaktivierte Regeln stehen im Bereich „Deaktiviert“ ohne Griff; aktive eigene Regeln vor deaktivierten | nach dem Schalter Regel im Bereich „Deaktiviert“; erwartete Reihenfolge nach Alt+↑ `[leer, beide, nur]` |
| `spec/test_openapi.py::test_alle_operationen_vorhanden` | D-308: neue Operation `GET /api/regeln/pruefung` | in `OPERATIONEN_M30` ergänzt |
| eigene `test_lernregeln_eigen.py`: `test_geloeschte_regel_entsteht_nicht_wieder`, `test_sicherung_enthaelt_vermerk_und_sperre` | D-308 | Löschen ohne Sperre; Sicherung mit deaktivierter Regel |
| eigene `test_browser_buchung_teilen.py` | D-310: Beschriftung nach den Symbolen im Teilen-Text | erwartete Zeilen mit „Datum:“, „Konto:“, „Kategorie:“ |
| `spec/test_openapi.py::test_m8_schemas`, `::test_m32_schemas`, eigene `test_m6_eigen.py::test_sicherung_der_schemaversion_2_…` | D-312: `KontoAenderung` mit `art` und `inhaber`, OpenAPI 2.26.0, Sicherung Schemaversion 12 | Felder ergänzt; Version „mindestens 2.25.0“; Schemaversion 12 |
| eigene `test_browser_mail_aktuell.py::test_abruf_im_hintergrund_aktualisiert_das_sichtbare_kontoblatt` | wacklig (D-287-Notiz, rot im CI-Lauf vom 2026-11-27): änderte den Bestand, bevor die Oberfläche den Stand beim Start gemerkt hatte | wartet nach dem Öffnen auf die erste Antwort von `/api/bestand/stand`; Erwartung unverändert |
- 2026-11-27 (D-313, nach dem Merge): `tests/test_browser_mail_aktuell.py::test_abruf_im_hintergrund_aktualisiert_das_sichtbare_kontoblatt`
  wartet vor der Änderung des Bestands auf Netzruhe. Sonst konnte eine noch laufende Abfrage `/api/bestand/stand`
  den geänderten Stand schon als gezeigten merken (in der CI rot, lokal grün). Prüfung unverändert.
- 2026-11-27 (D-317): `gesamt-tests/tests/app/m8/test_m8_kontoansicht.py` (Saldotext je Bestandskonto der
  Finanzübersicht) und eigene `tests/test_browser_konto_typ_inhaber.py`: Kreditkonten zeigen den Saldo dort jetzt
  umgedreht (Schulden positiv); `data-betrag` und Summe unverändert.
- 2026-11-27 (D-322): `gesamt-tests/tests/app/m22/test_m22_oberflaeche.py`: `FELDER_KONTO` und `FELDER_KATEGORIE` um die
  neue Spalte `saldo` („Summe“) ergänzt.
- 2026-11-28 (D-324): Personen kommen aus `KONTOR_BENUTZER`. `gesamt-tests/tests/hilfen/api.py` (`neue_config`) setzt
  ohne Angabe `benutzer=("Torsten", "Tina")`, damit die früheren Browsertests mit genau diesen Personen arbeiten;
  `gesamt-tests/tests/spec/test_openapi.py` erwartet zusätzlich `GET /api/benutzer`. Eigene Tests:
  `tests/test_browser.py` (`server`), `test_browser_kredit_spalten.py`, `test_browser_tabs.py`,
  `test_browser_tastatur.py` setzen dieselben zwei Personen; `tests/test_oberflaeche.py` kennt `/api/benutzer`.
- 2026-11-28 (D-326): `gesamt-tests/tests/spec/test_openapi.py` erwartet zusätzlich `POST /api/kategorien/verschieben`;
  `tests/test_oberflaeche.py` kennt den Pfad.
- 2026-11-28 (D-327): Liste aus `TESTUMBAU.md` hierher verlegt; neu `tests/test_browser_status_farben.py` (D-260, D-264, D-267).
