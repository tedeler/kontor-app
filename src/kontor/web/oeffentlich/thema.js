/* Kontor – Design vor dem ersten Zeichnen setzen (D-273).
 * Klassisches, blockierendes Skript im Kopf der Hülle, vor dem Stylesheet: Das Modul der Anwendung läuft erst nach dem
 * Einlesen der Seite, bis dahin wäre sie im hellen Design gezeichnet. Dieselbe Regel wie `thema` in app/haupt.js. */
(function () {
  var t = null;
  try { t = localStorage.getItem("kontor.thema"); } catch (e) { /* Speicher nicht verfügbar: wie das System */ }
  if (t !== "hell" && t !== "dunkel") {
    t = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dunkel" : "hell";
  }
  document.documentElement.dataset.thema = t;
}());
