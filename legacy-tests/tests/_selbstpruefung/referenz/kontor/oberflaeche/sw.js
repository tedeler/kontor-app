// WEGWERF-REFERENZ (E-149): Service Worker mit Hülle im Cache, nie /api/.
const CACHE = "kontor-referenz-1";
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(["/", "/oeffentlich/app.js", "/oeffentlich/app.css"])));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return;
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(() => caches.match("/")));
  } else if (url.pathname.startsWith("/oeffentlich/")) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
  }
});
