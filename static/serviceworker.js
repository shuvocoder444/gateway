/**
 * MFS Payment Gateway - Progressive Web App Service Worker
 * Version: 1.0.0
 */

const CACHE_VERSION = 'mfs-gateway-v1';
const PRECACHE_ASSETS = [
    '/dashboard/',
    '/manifest.json',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
    '/static/icons/icon.svg',
    '/static/icons/favicon.png',
    'https://cdn.tailwindcss.com',
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@500;600;700;800&display=swap'
];

// Offline fallback HTML
const OFFLINE_HTML = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Offline | MFS Gateway</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;700&family=Outfit:wght@700&display=swap" rel="stylesheet">
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-6 font-sans">
    <div class="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center shadow-2xl">
        <div class="w-16 h-16 bg-rose-500/10 text-rose-500 border border-rose-500/20 rounded-2xl flex items-center justify-center mx-auto mb-5">
            <svg class="w-8 h-8" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.828m2.829 2.828L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.828m-4.243 4.243a9 9 0 01-12.728 0m0 0l2.828-2.828m-2.828 2.828L3 21m2.828-5.657a5 5 0 010-7.072m0 0l2.828 2.828"></path>
            </svg>
        </div>
        <h1 class="text-xl font-bold font-['Outfit'] mb-2">You're Currently Offline</h1>
        <p class="text-xs text-slate-400 mb-6 leading-relaxed">
            MFS Gateway is in offline cache mode. Please check your internet connection to sync live transaction logs and verify payments.
        </p>
        <button onclick="window.location.reload()" class="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-rose-600 to-rose-700 hover:from-rose-500 hover:to-rose-600 text-white font-semibold text-xs transition shadow-lg shadow-rose-600/20">
            Retry Connection
        </button>
    </div>
</body>
</html>
`;

// 1. INSTALL: Pre-cache app shell and core assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_VERSION).then((cache) => {
            // Cache individual assets safely
            return Promise.allSettled(
                PRECACHE_ASSETS.map((url) =>
                    fetch(url, { mode: 'cors' })
                        .then((response) => {
                            if (response.ok) {
                                return cache.put(url, response);
                            }
                        })
                        .catch((err) => console.warn('[PWA SW] Precache skipped for:', url, err))
                )
            );
        }).then(() => self.skipWaiting())
    );
});

// 2. ACTIVATE: Clean old cache versions
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((name) => {
                    if (name !== CACHE_VERSION) {
                        return caches.delete(name);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// 3. FETCH: Strategy based on request type
self.addEventListener('fetch', (event) => {
    const request = event.request;
    const url = new URL(request.url);

    // Bypass non-GET requests (e.g. POST /api/...)
    if (request.method !== 'GET') {
        return;
    }

    // Skip Chrome extension requests or non-HTTP schemes
    if (!url.protocol.startsWith('http')) {
        return;
    }

    // Strategy A: APIs (/api/) -> Network Only with JSON offline fallback
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(request).catch(() => {
                return new Response(
                    JSON.stringify({
                        status: 'offline',
                        detail: 'Network unavailable. Operating in offline mode.'
                    }),
                    {
                        headers: { 'Content-Type': 'application/json' },
                        status: 503
                    }
                );
            })
        );
        return;
    }

    // Strategy B: Navigation (HTML pages) -> Network First with cache/offline fallback
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request)
                .then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const copy = networkResponse.clone();
                        caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
                    }
                    return networkResponse;
                })
                .catch(async () => {
                    const cachedResponse = await caches.match(request);
                    if (cachedResponse) {
                        return cachedResponse;
                    }
                    return new Response(OFFLINE_HTML, {
                        headers: { 'Content-Type': 'text/html' },
                        status: 200
                    });
                })
        );
        return;
    }

    // Strategy C: Static Assets (Images, Icons, Fonts, CSS) -> Cache First / Stale While Revalidate
    event.respondWith(
        caches.match(request).then((cachedResponse) => {
            const fetchPromise = fetch(request)
                .then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const copy = networkResponse.clone();
                        caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
                    }
                    return networkResponse;
                })
                .catch(() => cachedResponse);

            return cachedResponse || fetchPromise;
        })
    );
});
