import { NextResponse } from 'next/server';

import { listingServiceUrl } from '@/lib/api';
import { buyerBackendSend } from '@/lib/buyer-server-api';

/**
 * Buyer save/unsave proxy (SCRUM-95). POST saves a listing, DELETE unsaves it;
 * both forward to listing-service /listings/{id}/save with the buyer token.
 */
async function forward(method: 'POST' | 'DELETE', id: string): Promise<NextResponse> {
  const { status, body } = await buyerBackendSend(
    method,
    `${listingServiceUrl()}/listings/${encodeURIComponent(id)}/save`,
  );
  return NextResponse.json(body, { status });
}

export async function POST(_req: Request, { params }: { params: { id: string } }) {
  return forward('POST', params.id);
}

export async function DELETE(_req: Request, { params }: { params: { id: string } }) {
  return forward('DELETE', params.id);
}
