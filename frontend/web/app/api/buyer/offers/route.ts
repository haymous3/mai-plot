import { NextRequest, NextResponse } from 'next/server';

import { transactionServiceUrl } from '@/lib/api';
import { buyerBackendSend } from '@/lib/buyer-server-api';

/**
 * Buyer offer (Place a Bid) proxy (SCRUM-95). Forwards {listing_id, amount_kobo}
 * to transaction-service POST /transactions (create_offer) with the buyer token.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: { listing_id?: unknown; amount_kobo?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  const listing_id = typeof payload.listing_id === 'string' ? payload.listing_id : '';
  const amount_kobo = typeof payload.amount_kobo === 'number' ? payload.amount_kobo : 0;

  const { status, body } = await buyerBackendSend('POST', `${transactionServiceUrl()}/transactions`, {
    listing_id,
    amount_kobo,
  });
  return NextResponse.json(body, { status });
}
