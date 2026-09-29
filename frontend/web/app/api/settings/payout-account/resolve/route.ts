import { NextRequest, NextResponse } from 'next/server';

import { transactionServiceUrl } from '@/lib/api';
import { isCompleteAccountNumber } from '@/lib/payout-account';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * The name the BANK holds for an account (SCRUM-223) — transaction-service
 * `GET /payout-account/resolve`. Shown to the payee to confirm before saving;
 * nothing is stored. Inputs are shape-checked here so a half-typed number never
 * spends a call to the bank.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });

  const accountNumber = request.nextUrl.searchParams.get('account_number') ?? '';
  const bankCode = request.nextUrl.searchParams.get('bank_code') ?? '';
  if (!isCompleteAccountNumber(accountNumber) || !/^\d{3,10}$/.test(bankCode)) {
    return NextResponse.json({ error_code: 'VALIDATION_ERROR' }, { status: 422 });
  }

  const qs = new URLSearchParams({ account_number: accountNumber, bank_code: bankCode });
  try {
    const resp = await fetch(`${transactionServiceUrl()}/payout-account/resolve?${qs}`, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
    const body = await resp.json().catch(() => ({}));
    return NextResponse.json(body, { status: resp.status });
  } catch {
    return NextResponse.json({ error_code: 'RECIPIENT_UNAVAILABLE' }, { status: 502 });
  }
}
