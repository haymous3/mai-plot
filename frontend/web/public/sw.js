/*
 * Maihomme Web Push Service Worker (SCRUM-121).
 *
 * Receives push messages from notification-service (payload shape:
 * {title, body, type, reference_type, reference_id}) and shows a notification;
 * routes a click to the relevant page. Plain JS — served from /sw.js at scope /.
 */

// Activate immediately so a freshly registered worker handles pushes without a
// reload.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

/**
 * Where a notification click should land. The app is admin-only today, so
 * everything opens the app root; this is the single spot to add per-entity deep
 * links (e.g. /listings/<reference_id>) as those user pages ship. Kept in sync
 * with lib/push.ts clickTargetPath (which the app code + tests use).
 */
function clickTargetPath() {
  return '/';
}

self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (err) {
    payload = {};
  }

  const title = payload.title || 'Maihomme';
  const options = {
    body: payload.body || '',
    icon: '/icon-192.png',
    badge: '/badge-72.png',
    // Coalesce repeats about the same entity into one notification.
    tag: payload.reference_id || payload.type || undefined,
    data: {
      type: payload.type || null,
      reference_type: payload.reference_type || null,
      reference_id: payload.reference_id || null,
    },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const path = clickTargetPath(event.notification.data);
  const target = new URL(path, self.location.origin).href;

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Focus an already-open Maihomme tab if there is one; otherwise open a tab.
      for (const client of clientList) {
        if (client.url.startsWith(self.location.origin) && 'focus' in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
