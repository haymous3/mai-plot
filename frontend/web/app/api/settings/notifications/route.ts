import { NextRequest, NextResponse } from 'next/server';

import { notificationServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Notification channel preferences for the Settings "Notifications" tab
 * (SCRUM-188). Proxies notification-service `GET`/`PATCH
 * /notifications/preferences`.
 *
 * ⚠️ `marketing_enabled` is opt-IN while the other three are opt-out. NDPR
 * (§9) requires explicit consent for promotional messaging, so it defaults
 * false server-side; the transactional channels default true. See
 * notification-service migration 0005 before changing any default here.
 *
 * The field list below is an allowlist, so a new preference must be added in
 * BOTH places — it is otherwise dropped silently on the way through.
 *
 * PATCH is partial: only the channels present are changed, so toggling one
 * cannot clobber another.
 */

async function proxy(method: 'GET' | 'PATCH', body?: string): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${notificationServiceUrl()}/notifications/preferences`, {
      method,
      headers: {
        authorization: `Bearer ${token}`,
        ...(body ? { 'content-type': 'application/json' } : {}),
      },
      body,
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'NOTIFICATION_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const parsed = await resp.json().catch(() => ({}));
  return NextResponse.json(parsed, { status: resp.status });
}

export async function GET(): Promise<NextResponse> {
  return proxy('GET');
}

export async function PATCH(request: NextRequest): Promise<NextResponse> {
  let payload: Record<string, unknown>;
  try {
    payload = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  // Forward only the three real channels, and only when actually supplied —
  // sending null for an untouched channel would be indistinguishable from
  // "leave it alone" upstream, but sending an unknown key would be dropped
  // silently and look like a working control.
  const out: Record<string, boolean> = {};
  for (const key of [
    'push_enabled',
    'sms_enabled',
    'email_enabled',
    'marketing_enabled',
  ] as const) {
    if (typeof payload[key] === 'boolean') out[key] = payload[key] as boolean;
  }
  return proxy('PATCH', JSON.stringify(out));
}
