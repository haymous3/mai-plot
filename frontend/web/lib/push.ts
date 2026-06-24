/**
 * Browser-side Web Push client (SCRUM-121) — the frontend half of SCRUM-79.
 *
 * Registers the Service Worker, requests notification permission on a meaningful
 * action (never on load), subscribes via the PushManager, and stores/removes the
 * subscription through the same-origin admin proxy (which attaches the session
 * token). The VAPID public key comes from build-time env — the backend exposes
 * no endpoint for it.
 *
 * The pure helpers (urlBase64ToUint8Array, clickTargetPath) are unit-tested; the
 * navigator/PushManager calls only run in the browser.
 */

/** Base64url VAPID public key, surfaced to the client at build time. Empty when
 * unconfigured (e.g. local dev with the fake push backend) — callers treat an
 * empty key as "push unavailable". */
export const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? '';

/** Same-origin proxy that forwards to notification-service with the session
 * token attached server-side. */
const SUBSCRIPTIONS_ENDPOINT = '/api/admin/push/subscriptions';

/** The push payload the Service Worker + click handler receive (matches
 * notification-service PushSendService.send). */
export interface PushPayload {
  title: string | null;
  body: string;
  type: string;
  reference_type: string | null;
  reference_id: string | null;
}

/**
 * Decode a base64url VAPID public key into the Uint8Array the PushManager wants
 * as `applicationServerKey`. base64url → base64 (─/_ → +//), pad to a multiple
 * of 4, then decode each byte.
 */
export function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  // Back the array with a concrete ArrayBuffer so the result is a valid
  // BufferSource for PushManager.subscribe (not Uint8Array<ArrayBufferLike>).
  const output = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) {
    output[i] = raw.charCodeAt(i);
  }
  return output;
}

/**
 * Where a notification click should take the user, derived from the payload.
 * The app is admin-only today, so everything routes to the app root; this is the
 * single extension point as per-entity user pages ship. Always returns a
 * same-origin relative path and never throws on null fields.
 */
export function clickTargetPath(payload: Partial<PushPayload> | null | undefined): string {
  if (!payload) return '/';
  // Future: map reference_type → a deep link (e.g. `/listings/${reference_id}`)
  // once those user-facing pages exist.
  return '/';
}

/** Whether this browser can do Web Push at all (and we have a key to use). */
export function isPushSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    'serviceWorker' in navigator &&
    typeof window !== 'undefined' &&
    'PushManager' in window &&
    'Notification' in window &&
    VAPID_PUBLIC_KEY.length > 0
  );
}

/** Register the Service Worker (idempotent — the browser dedupes by URL/scope). */
export async function registerServiceWorker(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.register('/sw.js');
}

/** The active push subscription for this browser, if already subscribed. */
export async function getExistingSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.ready;
  return registration.pushManager.getSubscription();
}

export type SubscribeOutcome = 'subscribed' | 'denied' | 'unsupported';

/**
 * Request permission (the meaningful-action trigger), subscribe via the
 * PushManager, and persist the subscription. Returns 'denied' if the user
 * declines, 'unsupported' if the browser/key can't do push.
 */
export async function subscribeToPush(): Promise<SubscribeOutcome> {
  if (!isPushSupported()) return 'unsupported';

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return 'denied';

  const registration = await navigator.serviceWorker.ready;
  const existing = await registration.pushManager.getSubscription();
  const subscription =
    existing ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
    }));

  const resp = await fetch(SUBSCRIPTIONS_ENDPOINT, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(subscription.toJSON()),
  });
  if (!resp.ok) {
    // Don't leave a browser subscription the backend doesn't know about.
    await subscription.unsubscribe().catch(() => undefined);
    throw new Error(`Failed to store push subscription (${resp.status}).`);
  }
  return 'subscribed';
}

/** Remove the subscription from the backend, then from the browser. */
export async function unsubscribeFromPush(): Promise<void> {
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return;

  await fetch(SUBSCRIPTIONS_ENDPOINT, {
    method: 'DELETE',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ endpoint: subscription.endpoint }),
  }).catch(() => undefined);
  await subscription.unsubscribe();
}
