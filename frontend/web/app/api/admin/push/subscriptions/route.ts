import { NextRequest, NextResponse } from 'next/server';

import { notificationServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Same-origin proxy for Web Push subscription register/unregister (SCRUM-121).
 * The browser can't read the httpOnly session cookie, so it calls here and we
 * attach the bearer token server-side, forwarding to notification-service
 * POST/DELETE /notifications/push/subscriptions (SCRUM-79).
 */

const ENDPOINT = '/notifications/push/subscriptions';

function token(request: NextRequest): string | null {
  return request.cookies.get(ACCESS_COOKIE)?.value ?? null;
}

async function forward(
  request: NextRequest,
  method: 'POST' | 'DELETE',
  body: unknown,
): Promise<NextResponse> {
  const access = token(request);
  if (!access) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${notificationServiceUrl()}${ENDPOINT}`, {
      method,
      headers: { 'content-type': 'application/json', authorization: `Bearer ${access}` },
      body: JSON.stringify(body),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'PUSH_SUBSCRIPTION_FAILED';
    try {
      const errBody = (await resp.json()) as { error_code?: string };
      if (errBody.error_code) code = errBody.error_code;
    } catch {
      // keep default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }

  // 201 (register) returns {id}; 204 (unregister) is empty.
  if (resp.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  const data = await resp.json().catch(() => ({}));
  return NextResponse.json(data, { status: resp.status });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  return forward(request, 'POST', payload);
}

export async function DELETE(request: NextRequest): Promise<NextResponse> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  return forward(request, 'DELETE', payload);
}
