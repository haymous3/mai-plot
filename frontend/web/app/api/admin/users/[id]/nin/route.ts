import { NextRequest, NextResponse } from 'next/server';

import { forwardAdminNin as forward } from '@/lib/admin-nin-proxy';
import { authServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * NIN console proxies (SCRUM-224): masked status, set/replace, clear. The
 * reveal lives in ./reveal/route.ts because it is the one response that
 * carries the number and deserves its own file to be found in.
 *
 * Every write here needs a REASON — it is the audit row's answer to "why did
 * this admin change this person's national identity number" — so the proxy
 * refuses an empty one before spending a round trip. The API enforces the
 * same floor (10 characters).
 */

const REASON_MIN = 10;

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  return forward(`${authServiceUrl()}/admin/users/${params.id}/nin`, {
    method: 'GET',
    headers: { authorization: `Bearer ${token}` },
  });
}

/** PUT — create or replace. Only `nin` and `reason` travel. */
export async function PUT(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });

  let payload: { nin?: unknown; reason?: unknown };
  try {
    payload = (await request.json()) as { nin?: unknown; reason?: unknown };
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  const nin = typeof payload.nin === 'string' ? payload.nin.trim() : '';
  const reason = typeof payload.reason === 'string' ? payload.reason.trim() : '';
  if (!/^\d{11}$/.test(nin)) {
    return NextResponse.json({ error: 'NIN_FORMAT_INVALID' }, { status: 400 });
  }
  if (reason.length < REASON_MIN) {
    return NextResponse.json({ error: 'REASON_REQUIRED' }, { status: 400 });
  }

  return forward(`${authServiceUrl()}/admin/users/${params.id}/nin`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify({ nin, reason }),
  });
}

/** DELETE — clear, with the reason the console collects. */
export async function DELETE(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });

  let reason = '';
  try {
    const payload = (await request.json()) as { reason?: unknown };
    if (typeof payload.reason === 'string') reason = payload.reason.trim();
  } catch {
    // fall through to the reason check
  }
  if (reason.length < REASON_MIN) {
    return NextResponse.json({ error: 'REASON_REQUIRED' }, { status: 400 });
  }

  return forward(`${authServiceUrl()}/admin/users/${params.id}/nin`, {
    method: 'DELETE',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify({ reason }),
  });
}
