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

  // Fehlertext setzen: das Element ist nur mit Text sichtbar (oberflaeche.md 19, anmeldung-fehler)
  function zeige(text) {
    meldung.textContent = text;
    meldung.hidden = !text;
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
        zeige("Die Sperre ist abgelaufen. Bitte erneut versuchen.");
        return;
      }
      zeige("Zu viele falsche Versuche. Die Anmeldung ist noch " + rest + " s gesperrt.");
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
      // D-284: Anmeldung mit Passkey anbieten, wenn einer eingerichtet ist und der Browser es kann
      if (passkeyKnopf && !einrichten && d.passkeys && window.isSecureContext && window.PublicKeyCredential) passkeyKnopf.hidden = false;
    } catch (e) { /* Status ist nur ein Hinweis */ }
  }

  // ------------------------------------------------------------ Passkey (D-284, sicherheit.md 13)
  const passkeyKnopf = document.getElementById("anmeldung-passkey");
  const b64 = (p) => btoa(String.fromCharCode.apply(null, new Uint8Array(p))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const roh = (t) => Uint8Array.from(atob(t.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
  async function senden(pfad, koerper) {
    const r = await fetch(pfad, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(koerper || {}), credentials: "same-origin" });
    let d = null;
    try { d = await r.json(); } catch (e) { d = null; }
    return { ok: r.ok, daten: d };
  }
  if (passkeyKnopf) passkeyKnopf.addEventListener("click", async function () {
    meldung.className = "meldung";
    zeige("");
    passkeyKnopf.disabled = true;
    try {
      const o = await senden("/api/anmeldung/passkey/optionen");
      if (!o.ok) throw new Error("optionen");
      const cred = await navigator.credentials.get({ publicKey: Object.assign({}, o.daten, { challenge: roh(o.daten.challenge),
        allowCredentials: o.daten.allowCredentials.map((c) => ({ type: c.type, id: roh(c.id) })) }) });
      const a = cred.response;
      const r = await senden("/api/anmeldung/passkey", { kennung: b64(cred.rawId), client_daten: b64(a.clientDataJSON),
        auth_daten: b64(a.authenticatorData), signatur: b64(a.signature) });
      if (r.ok) { window.location.replace(ziel()); return; }
      zeige("Der Passkey wurde nicht anerkannt. Bitte mit dem Passwort anmelden.");
    } catch (e) {
      if (!(e && (e.name === "NotAllowedError" || e.name === "AbortError"))) zeige("Die Anmeldung mit Passkey ist fehlgeschlagen.");
    }
    passkeyKnopf.disabled = false;
  });

  formular.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    meldung.className = "meldung";
    zeige("");
    const passwort = formular.elements.passwort.value;
    const koerper = { passwort: passwort };
    if (einrichten) koerper.einrichtungscode = formular.elements.einrichtungscode.value.trim();
    if ([...passwort.normalize("NFC")].length < 12) {
      zeige("Das Passwort muss mindestens 12 Zeichen lang sein.");
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
      zeige(texte[code] || "Die Anmeldung ist fehlgeschlagen (Status " + r.status + ").");
      knopf.disabled = false;
      formular.elements.passwort.value = "";
      formular.elements.passwort.focus();
    } catch (e) {
      zeige("Der Server ist nicht erreichbar.");
      knopf.disabled = false;
    }
  });
  status();
})();
