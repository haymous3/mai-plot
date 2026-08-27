import { NextRequest, NextResponse } from 'next/server';

import { transactionServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Payout bank account for the Settings "Financial" tab (SCRUM-188).
 *
 * Proxies transaction-service `GET`/`PUT /payout-account`. The endpoints have
 * existed since SCRUM-145; its PR 4 was deferred for want of a design, and the
 * Financial tab is that design.
 *
 * The GET returns `account_number_masked` (last four only) — the full number is
 * never read back, so the form shows the mask and only sends a full number when
 * the user is replacing the account.
 */

async function proxy(method: 'GET' | 'PUT', body?: string): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${transactionServiceUrl()}/payout-account`, {
      method,
      headers: {
        authorization: `Bearer ${token}`,
        ...(body ? { 'content-type': 'application/json' } : {}),
      },
      body,
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'TRANSACTION_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const parsed = await resp.json().catch(() => ({}));
  return NextResponse.json(parsed, { status: resp.status });
}

export async function GET(): Promise<NextResponse> {
  return proxy('GET');
}

export async function PUT(request: NextRequest): Promise<NextResponse> {
  let payload: {
    account_number?: unknown;
    bank_code?: unknown;
    account_name?: unknown;
  };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  return proxy(
    'PUT',
    JSON.stringify({
      account_number: typeof payload.account_number === 'string' ? payload.account_number : '',
      bank_code: typeof payload.bank_code === 'string' ? payload.bank_code : '',
      account_name: typeof payload.account_name === 'string' ? payload.account_name : '',
    }),
  );
}
