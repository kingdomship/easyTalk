const CACHE_NAME = 'easytalk-v8';

// ── Install: precache core assets, activate immediately ────────────
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      cache.addAll([
        '/',
        '/style.css',
        '/js/engine.js',
        '/js/visuals.js',
        '/js/constellation.js',
        '/js/ui.js',
        '/manifest.json',
        '/icons/pwa-192.png',
        '/icons/pwa-512.png'
      ])
    )
  );
});

// ── Activate: claim all clients, purge old caches ─────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    Promise.all([
      self.clients.claim(),
      caches.keys().then(keys =>
        Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
      )
    ])
  );
});

// ── Fetch: route by request type ──────────────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // API requests: pass through — must not intercept SSE streams
  if (url.pathname.startsWith('/api/')) return;

  // Navigation: network-first, offline fallback to cache
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match('/'))
    );
    return;
  }

  // Static assets: cache-first
  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request))
  );
});
