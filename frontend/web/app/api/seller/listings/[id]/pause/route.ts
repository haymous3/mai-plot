import { NextResponse } from 'next/server';

import { listingServiceUrl } from '@/lib/api';
import { sessionBackendSend } from '@/lib/session-api';

/**
 * Seller pause/resume proxy (SCRUM-98). POST pauses a listing; DELETE resumes
 * it. Both forward to listing-service /listings/{id}/{pause,resume} with the
 * session token.
 */
async function forward(method: 'pause' | 'resume', id: string): Promise<NextResponse> {
  const { status, body } = await sessionBackendSend(
    'POST',
    `${listingServiceUrl()}/listings/${encodeURIComponent(id)}/${method}`,
  );
  return NextResponse.json(body, { status });
}

export async function POST(_req: Request, { params }: { params: { id: string } }) {
  return forward('pause', params.id);
}

export async function DELETE(_req: Request, { params }: { params: { id: string } }) {
  return forward('resume', params.id);
}
