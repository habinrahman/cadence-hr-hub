// Cadence service worker. It caches static build assets and the offline page only.
// It never touches the API origin, non-GET requests, HTML pages or RSC payloads,
// so candidate and hiring data never enter the browser cache.
const STATIC = "cadence-static-v2";
const OFFLINE_URL = "/offline.html"; // plain HTML with no scripts, so it still works when nothing else can load
const ASSETS = ["/icons/icon-192.png", "/icons/icon-512.png", OFFLINE_URL];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC)
      .then((cache) => cache.addAll(ASSETS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== STATIC).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  // The API lives on another origin. Leave it completely alone.
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/_next/static/")) {
    // Hashed, immutable build assets.
    event.respondWith(
      caches.open(STATIC).then(async (cache) => {
        const hit = await cache.match(request);
        if (hit) return hit;
        const response = await fetch(request);
        if (response.ok) cache.put(request, response.clone());
        return response;
      }),
    );
    return;
  }

  if (request.mode === "navigate") {
    // Always go to the network. Only when it fails show the static offline page.
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
  }
});
