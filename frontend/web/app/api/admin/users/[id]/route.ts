import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Proxies for editing and deleting a user (SCRUM-209). Attaches the admin access
 * token from the httpOnly cookie and forwards to auth-service, passing its
 * status + error_code through so the UI can distinguish every refusal — they mean
 * very different things here (409 "has deals" is temporary, 403 "staff" never
 * changes, 503 means nothing happened and a retry is the fix).
 */

/** PATCH — name / location / address only.
 *
 * The allowlist is enforced here as well as in the service: role, email and phone
 * must not travel even if a future form gains a field, because a proxy that
 * forwards whatever it is given is one edit away from being the escalation path
 * the API deliberately closed. */
export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });

  let payload: Record<string, unknown>;
  try {
    payload = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  const body: Record<string, unknown> = {};
  for (const field of ['full_name', 'location', 'address'] as const) {
    // `in` rather than a truthiness check: sending null CLEARS a location, and
    // omitting the key leaves it alone. Collapsing the two would make a value
    // impossible to remove once set.
    if (field in payload) body[field] = payload[field];
  }
  if (Object.keys(body).length === 0) {
    return NextResponse.json({ error: 'NOTHING_TO_UPDATE' }, { status: 400 });
  }

  return forward(`${authServiceUrl()}/admin/users/${params.id}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
}

/** DELETE — soft delete, with the reason the console collects in its modal. */
export async function DELETE(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });

  let reason: string | undefined;
  try {
    const payload = (await request.json()) as { reason?: unknown };
    if (typeof payload.reason === 'string') reason = payload.reason;
  } catch {
    // A delete with no body is fine — the reason is optional on the API.
  }

  return forward(`${authServiceUrl()}/admin/users/${params.id}`, {
    method: 'DELETE',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify({ reason }),
  });
}

async function forward(url: string, init: RequestInit): Promise<NextResponse> {
  let resp: Response;
  try {
    resp = await fetch(url, { ...init, cache: 'no-store' });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'REQUEST_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep the default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }
  return NextResponse.json(await resp.json());
}
