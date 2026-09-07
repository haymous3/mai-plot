import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Suspend / reactivate proxy (SCRUM-209).
 *
 * The action is an ALLOWLIST, not a passthrough: `params.action` is interpolated
 * into the upstream URL, so accepting whatever arrives would let a crafted path
 * reach any POST endpoint on auth-service under an admin's token.
 */
const ACTIONS = new Set(['suspend', 'reactivate']);

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string; action: string } },
): Promise<NextResponse> {
  if (!ACTIONS.has(params.action)) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });

  // Suspending needs a reason (the audit row is what a colleague reads before
  // undoing it); reactivating takes no body at all.
  let body = '{}';
  if (params.action === 'suspend') {
    let reason = '';
    try {
      const payload = (await request.json()) as { reason?: unknown };
      if (typeof payload.reason === 'string') reason = payload.reason.trim();
    } catch {
      // fall through to the empty-reason check
    }
    if (!reason) return NextResponse.json({ error: 'REASON_REQUIRED' }, { status: 400 });
    body = JSON.stringify({ reason });
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/admin/users/${params.id}/${params.action}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body,
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'REQUEST_FAILED';
    try {
      const payload = (await resp.json()) as { error_code?: string };
      if (payload.error_code) code = payload.error_code;
    } catch {
      // keep the default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }
  return NextResponse.json(await resp.json());
}
