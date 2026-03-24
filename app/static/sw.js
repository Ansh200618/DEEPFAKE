/* ═══════════════════════════════════════════════════════
   DeepGuard Service Worker  –  v1.0.0
   Strategy: Cache-first for static assets,
             Network-first for API calls,
             Offline fallback for the UI shell.
   ═══════════════════════════════════════════════════════ */

const CACHE_VERSION  = 'deepguard-v1.0.0';
const STATIC_CACHE   = `${CACHE_VERSION}-static`;
const API_CACHE      = `${CACHE_VERSION}-api`;

/* Assets to pre-cache at install time (app shell) */
const PRECACHE_URLS = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/offline.html',
];

/* ── Install ──────────────────────────────────────────── */
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      /* Use individual adds so one 404 doesn't block the rest */
      return Promise.allSettled(
        PRECACHE_URLS.map(url =>
          cache.add(url).catch(err =>
            console.warn(`[SW] Pre-cache failed for ${url}:`, err)
          )
        )
      );
    }).then(() => self.skipWaiting())
  );
});

/* ── Activate – clean up old caches ──────────────────── */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k.startsWith('deepguard-') && k !== STATIC_CACHE && k !== API_CACHE)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

/* ── Fetch ────────────────────────────────────────────── */
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  /* Skip non-GET and cross-origin requests */
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  /* API endpoints: network-first, short cache for GET health check */
  if (url.pathname.startsWith('/api/')) {
    if (url.pathname === '/api/health') {
      event.respondWith(networkFirst(request, API_CACHE, 60));
    }
    /* POST detect endpoints – never cache, always live */
    return;
  }

  /* Static assets: cache-first */
  if (
    url.pathname.startsWith('/static/') ||
    url.pathname === '/manifest.json'
  ) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  /* Navigation (HTML pages): network-first with offline fallback */
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(resp => {
          const clone = resp.clone();
          caches.open(STATIC_CACHE).then(c => c.put(request, clone));
          return resp;
        })
        .catch(() =>
          caches.match(request)
            .then(cached => cached || caches.match('/offline.html'))
        )
    );
    return;
  }

  /* Default: stale-while-revalidate */
  event.respondWith(staleWhileRevalidate(request, STATIC_CACHE));
});

/* ── Background Sync for queued analyses ─────────────── */
self.addEventListener('sync', event => {
  if (event.tag === 'deepguard-sync') {
    event.waitUntil(flushQueue());
  }
});

async function flushQueue() {
  /* Placeholder for offline-queued analyses */
  const clients = await self.clients.matchAll();
  clients.forEach(c => c.postMessage({ type: 'SYNC_COMPLETE' }));
}

/* ── Push notifications ──────────────────────────────── */
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(
    self.registration.showNotification(data.title || 'DeepGuard Alert', {
      body:    data.body    || 'A new analysis result is available.',
      icon:    '/static/icons/icon-192.png',
      badge:   '/static/icons/icon-96.png',
      vibrate: [200, 100, 200],
      data:    { url: data.url || '/' },
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    self.clients.openWindow(event.notification.data.url || '/')
  );
});

/* ══════════════════ Cache Strategies ════════════════════ */

/** Cache-first: return cached copy; fetch & update in background if missing. */
async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const resp  = await fetch(request);
    const cache = await caches.open(cacheName);
    cache.put(request, resp.clone());
    return resp;
  } catch {
    return new Response('Offline', { status: 503 });
  }
}

/** Network-first: try network; fall back to cache. */
async function networkFirst(request, cacheName, maxAgeSeconds = 300) {
  try {
    const resp  = await fetch(request);
    const cache = await caches.open(cacheName);
    cache.put(request, resp.clone());
    return resp;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response(JSON.stringify({ error: 'offline' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } });
  }
}

/** Stale-while-revalidate: return cache immediately and update in background. */
async function staleWhileRevalidate(request, cacheName) {
  const cache  = await caches.open(cacheName);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request).then(resp => {
    cache.put(request, resp.clone());
    return resp;
  }).catch(() => null);

  return cached || fetchPromise || new Response('Offline', { status: 503 });
}
