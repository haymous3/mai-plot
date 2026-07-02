import { NextResponse } from 'next/server';

import { loanServiceUrl } from '@/lib/api';
import { buyerBackendSend } from '@/lib/buyer-server-api';

/** Same-origin proxy for a single loan's detail (SCRUM-94). Used by the status
 * page's 30s polling; forwards to loan-service GET /loans/{id} with the buyer
 * token. */
export async function GET(
  _request: Request,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const { status, body } = await buyerBackendSend(
    'GET',
    `${loanServiceUrl()}/loans/${encodeURIComponent(params.id)}`,
  );
  return NextResponse.json(body, { status });
}
