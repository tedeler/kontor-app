/* Kontor – Service Worker (oberflaeche.md 18, E-146).
 * Zwischengespeichert werden nur die Hülle und die statischen Dateien (Caches „kontor-…“), nie Antworten unter /api/.
 * Navigationen: zuerst Netz, bei Netzfehler die zwischengespeicherte Hülle. Statische Dateien: zuerst Netz, offline
 * aus dem Cache. */
const CACHE = "kontor-huelle-4";
const DATEIEN = [
  "/",
  "/oeffentlich/app.css",
  "/oeffentlich/app/haupt.js",
  "/oeffentlich/app/kern.js",
  "/oeffentlich/app/ui.js",
  "/oeffentlich/app/baum.js",
  "/oeffentlich/app/konto.js",
  "/oeffentlich/app/seiten.js",
  "/oeffentlich/app/tabs.js",
  "/oeffentlich/app/dokumente.js",
  "/oeffentlich/vendor/plotly-basic.min.js",
  "/oeffentlich/icon.svg",
  "/oeffentlich/icon-192.png",
  "/oeffentlich/icon-512.png",
  "/oeffentlich/icon-maskable-512.png",
  "/oeffentlich/manifest.webmanifest",
];

async function ablegen(cache, url) {
  try {
    const r = await fetch(url, { cache: "no-store", redirect: "manual", credentials: "same-origin" });
    if (r.ok && r.type === "basic") await cache.put(url, r);
  } catch (e) {
    /* ohne Netz: beim nächsten Abruf */
  }
}

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(CACHE).then((c) => Promise.all(DATEIEN.map((u) => ablegen(c, u)))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(caches.keys()
    .then((namen) => Promise.all(namen.filter((n) => n.startsWith("kontor-") && n !== CACHE).map((n) => caches.delete(n))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (ev) => {
  const req = ev.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;   // nie Daten zwischenspeichern
  if (req.mode === "navigate") {
    ev.respondWith(fetch(req).then((r) => {
      // jede Route liefert dieselbe Hülle ohne Buchbestand (oberflaeche.md 2): als „/“ aktuell halten
      if (r.ok && !r.redirected && r.type === "basic" && (r.headers.get("content-type") || "").startsWith("text/html")
          && url.pathname !== "/anmelden") {
        const kopie = r.clone();
        caches.open(CACHE).then((c) => c.put("/", kopie));
      }
      return r;
    }).catch(() => caches.open(CACHE).then((c) => c.match("/")).then((r) => r || Response.error())));
    return;
  }
  if (!DATEIEN.includes(url.pathname) || url.search) return;
  ev.respondWith(fetch(req).then((r) => {
    if (r.ok && r.type === "basic") {
      const kopie = r.clone();
      caches.open(CACHE).then((c) => c.put(url.pathname, kopie));
    }
    return r;
  }).catch(() => caches.open(CACHE).then((c) => c.match(url.pathname)).then((r) => r || Response.error())));
});
