const CACHE_NAME = 'hostel-app-v3';
const API_CACHE = 'api-cache-v1';

// Кешируем статику
const ASSETS = [
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
    '/manifest.json'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(ASSETS))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => Promise.all(
            keys.filter(key => key !== CACHE_NAME && key !== API_CACHE)
                .map(key => caches.delete(key))
        )).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    // API запросы (GET) - кешируем с обновлением (stale-while-revalidate)
    if (url.pathname.startsWith('/api/') && event.request.method === 'GET') {
        event.respondWith(
            caches.open(API_CACHE).then(cache => {
                return cache.match(event.request).then(cachedResponse => {
                    const fetchPromise = fetch(event.request).then(networkResponse => {
                        cache.put(event.request, networkResponse.clone());
                        return networkResponse;
                    }).catch(() => cachedResponse);

                    return cachedResponse || fetchPromise;
                });
            })
        );
        return;
    }

    // Статика
    event.respondWith(
        caches.match(event.request).then(response => {
            return response || fetch(event.request).then(resp => {
                if (event.request.method === 'GET') {
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, resp.clone()));
                }
                return resp;
            }).catch(() => caches.match('/'));
        })
    );
});