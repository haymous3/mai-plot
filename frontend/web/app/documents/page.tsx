import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { DocumentsClient } from './documents-client';
import { documentServiceUrl } from '@/lib/api';
import { roleHome, SESSION_LOGIN } from '@/lib/session';
import { sessionAccessToken, sessionRole } from '@/lib/session-server';
import type { UserDocuments } from '@/lib/user-documents';

export const metadata: Metadata = { title: 'My Documents · Maihomme' };

/**
 * My Documents — SCRUM-188.
 *
 * Server-rendered so the list and its counts are present before paint. Lives
 * outside the (buyer) route group for the same reason Settings does: the
 * design replaces the app header with its own bar, and personal documents
 * belong to every role, not just buyers.
 */

const EMPTY: UserDocuments = {
  items: [],
  category_counts: { identity: 0, financial: 0, property: 0, other: 0 },
  status_counts: { pending: 0, verified: 0, failed: 0, under_review: 0 },
  total: 0,
};

export default async function DocumentsPage() {
  const token = sessionAccessToken();
  if (!token) redirect(SESSION_LOGIN);

  let documents = EMPTY;
  try {
    const resp = await fetch(`${documentServiceUrl()}/documents/personal`, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
    if (resp.ok) documents = (await resp.json()) as UserDocuments;
  } catch {
    // A document-service outage degrades to an empty page the user can still
    // navigate away from, rather than a 500. Uploading will surface the real
    // error if the service is still down.
  }

  return <DocumentsClient initial={documents} home={roleHome(sessionRole() ?? 'buyer')} />;
}
