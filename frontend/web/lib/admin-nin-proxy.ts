import { NextResponse } from 'next/server';

/**
 * Shared forwarder for the NIN console proxies (SCRUM-224).
 *
 * Like the `forward` in app/api/admin/users/[id]/route.ts it passes status +
 * error_code through, but ALSO `details`: a registry rejection (422
 * NIN_NOT_VERIFIED) names which fields mismatched, and that is what the admin
 * needs to see to tell a typo from the wrong person. Lives in lib/ because a
 * route.ts may only export HTTP handlers.
 */
export async function forwardAdminNin(url: string, init: RequestInit): Promise<NextResponse> {
  let resp: Response;
  try {
    resp = await fetch(url, { ...init, cache: 'no-store' });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'REQUEST_FAILED';
    let details: unknown = undefined;
    try {
      const body = (await resp.json()) as { error_code?: string; details?: unknown };
      if (body.error_code) code = body.error_code;
      details = body.details;
    } catch {
      // keep the default
    }
    return NextResponse.json({ error: code, details }, { status: resp.status });
  }
  return NextResponse.json(await resp.json());
}
