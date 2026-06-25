import { NextRequest, NextResponse } from 'next/server';

import { notificationServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Same-origin proxy for notification channel preferences (SCRUM-125). Attaches
 * the session token from the httpOnly cookie and forwards to notification-service
 * GET / PATCH /notifications/preferences (SCRUM-122). PATCH takes a partial
 * {push_enabled?, sms_enabled?, email_enabled?} and returns the full new state.
 */

const ENDPOINT = '/notifications/preferences';

function token(request: NextRequest): string | null {
  return request.cookies.get(ACCESS_COOKIE)?.value ?? null;
}

async function relay(resp: Response): Promise<NextResponse> {
  if (!resp.ok) {
    let code = 'PREFERENCES_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }
  const data = await resp.json();
  return NextResponse.json(data);
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const access = token(request);
  if (!access) return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  try {
    const resp = await fetch(`${notificationServiceUrl()}${ENDPOINT}`, {
      headers: { authorization: `Bearer ${access}` },
      cache: 'no-store',
    });
    return relay(resp);
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }
}

export async function PATCH(request: NextRequest): Promise<NextResponse> {
  const access = token(request);
  if (!access) return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  try {
    const resp = await fetch(`${notificationServiceUrl()}${ENDPOINT}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${access}` },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });
    return relay(resp);
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }
}
