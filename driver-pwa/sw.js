const CACHE = '3ll-driver-v2';
const ASSETS = [
  '/driver-pwa/3lakesMobile.html',
  '/driver-pwa/login.html',
  '/driver-pwa/manifest.json',
  '/driver-pwa/icons/icon-192.png',
  '/driver-pwa/icons/icon-512.png',
  '/driver-pwa/icons/icon-512-maskable.png',
  '/driver-pwa/icons/apple-touch-icon.png',
  '/driver-pwa/icons/icon-120.png',
  '/driver-pwa/icons/icon-152.png',
  '/driver-pwa/icons/icon-167.png',
  '/driver-pwa/icons/icon-180.png',
  '/shared/config.js',
  '/shared/tk.js',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS).catch(() => {})));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  if (e.request.url.includes('/api/')) return;
  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request).then(cached => {
        if (cached) return cached;
        // Offline fallback for navigation requests
        if (e.request.mode === 'navigate') {
          return caches.match('/driver-pwa/3lakesMobile.html');
        }
      }))
  );
});

self.addEventListener('push', e => {
  const data = e.data?.json() || {};
  e.waitUntil(self.registration.showNotification(
    data.title || '3 Lakes Driver',
    {
      body: data.body || '',
      icon: '/driver-pwa/icons/icon-192.png',
      badge: '/driver-pwa/icons/icon-192.png',
      data,
    }
  ));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow('/driver-pwa/3lakesMobile.html'));
});
