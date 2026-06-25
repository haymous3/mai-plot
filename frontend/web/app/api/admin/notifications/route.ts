import { NextRequest, NextResponse } from 'next/server';

import { notificationServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Same-origin proxy for the in-app notification list (SCRUM-124). Attaches the
 * session token from the httpOnly cookie and forwards to notification-service
 * GET /notifications (SCRUM-82), passing the `limit`/`cursor` query through and
 * surfacing the X-Unread-Count header back to the client.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }

  const incoming = request.nextUrl.searchParams;
  const url = new URL(`${notificationServiceUrl()}/notifications`);
  const limit = incoming.get('limit');
  const cursor = incoming.get('cursor');
  if (limit) url.searchParams.set('limit', limit);
  if (cursor) url.searchParams.set('cursor', cursor);

  let resp: Response;
  try {
    resp = await fetch(url, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'NOTIFICATIONS_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }

  const data = await resp.json();
  const out = NextResponse.json(data);
  const unread = resp.headers.get('x-unread-count');
  if (unread) out.headers.set('x-unread-count', unread);
  return out;
}
