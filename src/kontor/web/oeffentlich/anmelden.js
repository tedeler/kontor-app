// Anmeldeseite (sicherheit.md 3.4, 4.2, 5): sendet nur per fetch an die REST-Schnittstelle.
(function () {
  "use strict";
  const formular = document.getElementById("anmeldung-formular");
  const meldung = document.getElementById("anmeldung-meldung");
  const knopf = formular.querySelector("button[type=submit]");
  const einrichten = formular.dataset.art === "einrichten";

  // Weiterleitung nur auf eigene Pfade: genau ein "/" am Anfang (kein "//", kein "/\")
  function ziel() {
    const w = new URLSearchParams(window.location.search).get("weiter") || "";
    if (w.length > 0 && w[0] === "/" && w[1] !== "/" && w[1] !== "\\") return w;
    return "/";
  }

  let sperreTimer = null;
  function sperreAnzeigen(bis) {
    clearInterval(sperreTimer);
    const ende = Date.parse(bis);
    knopf.disabled = true;
    meldung.className = "meldung sperre";
    function zeigen() {
      const rest = Math.ceil((ende - Date.now()) / 1000);
      if (!(rest > 0)) {
        clearInterval(sperreTimer);
        knopf.disabled = false;
        meldung.className = "meldung";
        meldung.textContent = "Die Sperre ist abgelaufen. Bitte erneut versuchen.";
        return;
      }
      meldung.textContent = "Zu viele falsche Versuche. Die Anmeldung ist noch " + rest + " s gesperrt.";
    }
    zeigen();
    sperreTimer = setInterval(zeigen, 1000);
  }

  async function status() {
    try {
      const r = await fetch("/api/anmeldung", { cache: "no-store" });
      const d = await r.json();
      if (d.angemeldet) window.location.replace(ziel());
      else if (d.gesperrt_bis) sperreAnzeigen(d.gesperrt_bis);
    } catch (e) { /* Status ist nur ein Hinweis */ }
  }

  formular.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    meldung.className = "meldung";
    meldung.textContent = "";
    const passwort = formular.elements.passwort.value;
    const koerper = { passwort: passwort };
    if (einrichten) koerper.einrichtungscode = formular.elements.einrichtungscode.value.trim();
    if ([...passwort.normalize("NFC")].length < 12) {
      meldung.textContent = "Das Passwort muss mindestens 12 Zeichen lang sein.";
      return;
    }
    knopf.disabled = true;
    try {
      const r = await fetch(einrichten ? "/api/anmeldung/einrichten" : "/api/anmeldung", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(koerper),
        credentials: "same-origin" });
      let d = null;
      try { d = await r.json(); } catch (e) { d = null; }
      if (r.ok) { window.location.replace(ziel()); return; }
      const code = d && d.fehler ? d.fehler.code : "";
      if (code === "anmeldung_gesperrt") { sperreAnzeigen(d.fehler.details.gesperrt_bis); return; }
      const texte = {
        anmeldung_fehlgeschlagen: "Das Passwort ist falsch.",
        einrichtungscode_ungueltig: "Der Einrichtungscode ist falsch.",
        nicht_eingerichtet: "Kontor ist noch nicht eingerichtet. Bitte die Seite neu laden.",
        bereits_eingerichtet: "Kontor ist bereits eingerichtet. Bitte die Seite neu laden.",
        validierung: "Bitte die Eingaben prüfen (Passwort 12 bis 1024 Zeichen).",
        csrf_ungueltig: "Die Anfrage wurde abgelehnt (fremde Herkunft).",
        netz_nicht_erlaubt: "Zugriff nur aus dem Heimnetz.",
      };
      meldung.textContent = texte[code] || "Die Anmeldung ist fehlgeschlagen (Status " + r.status + ").";
      knopf.disabled = false;
      formular.elements.passwort.select();
    } catch (e) {
      meldung.textContent = "Der Server ist nicht erreichbar.";
      knopf.disabled = false;
    }
  });
  status();
})();
