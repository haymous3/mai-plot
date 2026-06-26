import { NextRequest, NextResponse } from 'next/server';

import { loanServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Same-origin proxy for one loan's repayment schedule (SCRUM-77). Attaches the
 * session token from the httpOnly cookie and forwards to loan-service GET
 * /loans/{id}/repayments, which authorises the caller (buyer-owns-or-admin) and
 * returns the milestone breakdown for the admin drill-down. Errors pass the
 * backend status + code straight back so the client can branch (403/404).
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${loanServiceUrl()}/loans/${params.id}/repayments`, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'REPAYMENTS_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }

  return NextResponse.json(await resp.json());
}
