import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl, transactionServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Payout bank account proxy — role-agnostic (SCRUM-145 / SCRUM-188; SCRUM-223).
 *
 * GET mirrors transaction-service `GET /payout-account` (last four digits only).
 *
 * PUT does the whole guarded save in ONE server round trip (SCRUM-223):
 *   1. POST auth-service /auth/reauth with the password the person just typed,
 *   2. PUT transaction-service /payout-account with the reauth token it returns
 *      in `X-Reauth-Token`.
 * The reauth token therefore never reaches browser JavaScript — it lives for
 * the length of this request, the same way the session token never leaves the
 * server. The password is forwarded once, as at sign-in, and never stored.
 *
 * Only `account_number` and `bank_code` are forwarded to the save: the name is
 * the bank's (transaction-service resolves it), so nothing typed can reach it.
 */

type Upstream = { status: number; body: Record<string, unknown> };

async function call(url: string, init: RequestInit): Promise<Upstream | null> {
  try {
    const resp = await fetch(url, { ...init, cache: 'no-store' });
    const body = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
    return { status: resp.status, body };
  } catch {
    return null;
  }
}

const unavailable = () =>
  NextResponse.json({ error_code: 'RECIPIENT_UNAVAILABLE' }, { status: 502 });

export async function GET(): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  const result = await call(`${transactionServiceUrl()}/payout-account`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!result) return unavailable();
  return NextResponse.json(result.body, { status: result.status });
}

export async function PUT(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });

  let payload: { account_number?: unknown; bank_code?: unknown; password?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  const accountNumber = typeof payload.account_number === 'string' ? payload.account_number : '';
  const bankCode = typeof payload.bank_code === 'string' ? payload.bank_code : '';
  const password = typeof payload.password === 'string' ? payload.password : '';
  if (!accountNumber || !bankCode || !password) {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  const reauth = await call(`${authServiceUrl()}/auth/reauth`, {
    method: 'POST',
    headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  if (!reauth) return unavailable();
  const reauthToken = reauth.body.reauth_token;
  if (reauth.status !== 200 || typeof reauthToken !== 'string') {
    return NextResponse.json(reauth.body, { status: reauth.status });
  }

  const saved = await call(`${transactionServiceUrl()}/payout-account`, {
    method: 'PUT',
    headers: {
      authorization: `Bearer ${token}`,
      'content-type': 'application/json',
      'x-reauth-token': reauthToken,
    },
    body: JSON.stringify({ account_number: accountNumber, bank_code: bankCode }),
  });
  if (!saved) return unavailable();
  return NextResponse.json(saved.body, { status: saved.status });
}
