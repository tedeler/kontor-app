"""Entwicklungstests zu D-253: Inhalte werden in Teilen geladen und je Teil gespeichert; ein Abbruch unterwegs
verliert nichts. Synthetische Daten; ersetzen nicht die Abnahmetests."""

from __future__ import annotations

from kontor.fehler import MailVerbindungsFehler
from kontor.plugins import imap

from .test_kopfabruf_eigen import (MAILS, Attrappe, imap_umgebung, nachricht, spiegel, umgebung)  # noqa: F401


class BrichtAb(Attrappe):
    """Gibt den ersten Teil ab und bricht dann die Verbindung ab (wie ein Abbruch mitten im Laden)."""

    def __init__(self, liste):
        super().__init__(liste)
        self.abbrechen = True

    def inhalte(self, postfach, koepfe, fortschritt=None, abgeben=None):
        if not self.abbrechen:
            return super().inhalte(postfach, koepfe, fortschritt, abgeben)
        self.verlangt.append(sorted(k.nachricht_id for k in koepfe))
        je_id = {n.nachricht_id: n for n in self.liste}
        erste = koepfe[0]
        abgeben({erste.nachricht_id: je_id[erste.nachricht_id]})
        raise MailVerbindungsFehler("Die Verbindung zum Mailserver wurde unterbrochen.")


AMAZON = [nachricht(f"<z{i}@x.invalid>", "versand@amazon.example.invalid", f"Versandt {i}", f"Text {i}", tag=12)
          for i in range(5)]


def test_abbruch_beim_laden_der_inhalte_verliert_nichts(umgebung):
    c, cfg, _ = umgebung
    p = BrichtAb([*MAILS, *AMAZON])
    c.app.state.sync.mail._mock_plugin = p
    erg = c.post("/api/mail/abruf").json()["postfaecher"][0]
    assert erg["status"] == "fehlgeschlagen" and erg["fehler"]["code"] == "mail_verbindung"
    s = spiegel(cfg)
    assert len(s) == 9                                    # alle Kopfzeilen sind gespeichert
    assert sum(r["inhalt"] for r in s.values()) == 1      # der erste Teil auch
    assert c.get("/api/mail/postfaecher/1/status").json()["letzter_erfolg_am"] is None
    p.abbrechen = False
    erg = c.post("/api/mail/abruf").json()["postfaecher"][0]
    assert erg["status"] == "erfolgreich" and erg["nachrichten_neu"] == 0 and erg["nachrichten_nachgeladen"] == 6
    s = spiegel(cfg)
    assert {n for n, r in s.items() if not r["inhalt"]} == {"<n1@x.invalid>", "<n3@x.invalid>"}


def test_imap_laedt_inhalte_in_teilen(imap_umgebung, monkeypatch):
    c, cfg, server = imap_umgebung
    monkeypatch.setattr(imap, "_TEIL", 1)
    teile = []
    original = c.app.state.sync.mail._inhalt_eintragen

    def zaehlen(con, cf, n):
        teile.append(n.nachricht_id)
        return original(con, cf, n)

    monkeypatch.setattr(c.app.state.sync.mail, "_inhalt_eintragen", zaehlen)
    from kontor.anbieter import aus_toml
    from kontor import anbieter
    alle = aus_toml("""name = "alle"\ntitel = "Alle"\n[vorauswahl]\nbetreff = 'fiktiv'\n[kennung]\nmuster = '(x)'
[[art]]\nname = "a"\nrolle = "ausgabe"\ngrund = "bestellung"\nbetreff = 'nie'\ngesamt = { fest = 0 }\n""")
    monkeypatch.setattr(anbieter, "aktive", lambda: (*anbieter.eingebaute(), alle))
    erg = c.post("/api/mail/abruf").json()["postfaecher"][0]
    assert erg["status"] == "erfolgreich" and erg["nachrichten_ohne_inhalt"] == 0, erg
    assert [a for a in server.abrufe if a[1] == "voll"] == [("1", "voll"), ("2", "voll"), ("3", "voll")]
    assert sorted(teile) == ["<n1@example.invalid>", "<n2@example.invalid>", "<p1@example.invalid>"]
