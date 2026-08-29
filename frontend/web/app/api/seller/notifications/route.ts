import { NextRequest, NextResponse } from 'next/server';

import { notificationServiceUrl } from '@/lib/api';
import { isInboxTab } from '@/lib/notification-inbox';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Seller notification inbox proxy (SCRUM-194). Forwards to notification-service
 * GET /notifications with the session token kept server-side, passing the
 * category tab and search term through.
 *
 * The page itself reads the feed server-side; this exists for the client-side
 * refresh after marking something read, and mirrors the buyer proxy.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  const url = new URL(`${notificationServiceUrl()}/notifications`);

  // Only ever a known tab is forwarded. "all" is the ABSENCE of a category, so
  // it is dropped rather than sent — the backend Literal would 422 on it.
  const tab = request.nextUrl.searchParams.get('category') ?? undefined;
  if (isInboxTab(tab) && tab !== 'all') {
    url.searchParams.set('category', tab);
  }

  const q = request.nextUrl.searchParams.get('q');
  if (q && q.trim()) url.searchParams.set('q', q.trim());

  const cursor = request.nextUrl.searchParams.get('cursor');
  if (cursor) url.searchParams.set('cursor', cursor);

  let resp: Response;
  try {
    resp = await fetch(url.toString(), {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'REQUEST_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep default
    }
    return NextResponse.json({ error_code: code }, { status: resp.status });
  }

  return NextResponse.json(await resp.json());
}
