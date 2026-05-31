const CACHE = '3ll-driver-v2';
const ASSETS = [
  '/', '/driver-pwa/',
  '/driver-pwa/index.html',
  '/driver-pwa/login.html',
  '/driver-pwa/lf.html',
  '/driver-pwa/login-lf.html',
  '/driver-pwa/manifest.json',
  '/driver-pwa/manifest-lf.json',
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
  if (e.request.url.includes('/api/')) return; // never cache API calls
  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

self.addEventListener('push', e => {
  const data = e.data?.json() || {};
  e.waitUntil(
    self.registration.showNotification(
      data.title || '3 Lakes Driver',
      { body: data.body || '', icon: '/favicon.ico', badge: '/favicon.ico', data }
    ).then(() =>
      self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients =>
        clients.forEach(c => c.postMessage({ type: 'PUSH_NOTIFICATION', title: data.title, body: data.body, data }))
      )
    )
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow('/driver-pwa/'));
});
