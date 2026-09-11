import { NextRequest, NextResponse } from 'next/server';

import { forwardAdminNin as forward } from '@/lib/admin-nin-proxy';
import { authServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Reveal proxy (SCRUM-224) — the ONE response on the platform that carries a
 * NIN in full. It is a POST with a mandatory reason: the API writes an audit
 * row (`user.nin_revealed_by_admin`) naming the admin, the user and the reason
 * in the same transaction as the decrypt, so there is no reveal without a
 * record. `no-store` on the upstream fetch and the JSON response below means
 * the number is never cached on this hop either.
 */
export async function POST(
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
  if (reason.length < 10) {
    return NextResponse.json({ error: 'REASON_REQUIRED' }, { status: 400 });
  }

  const resp = await forward(`${authServiceUrl()}/admin/users/${params.id}/nin/reveal`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify({ reason }),
  });
  resp.headers.set('cache-control', 'no-store');
  return resp;
}
