/**
 * Display helpers for the admin document review queue (SCRUM-192).
 *
 * The queue serves two tables through one endpoint, and they describe
 * themselves differently: property documents are a fixed set of legal types,
 * personal documents carry whatever filename their owner uploaded them under.
 */

import type { DocQueueItem } from './api';

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  c_of_o: 'Certificate of Occupancy',
  deed_of_assignment: 'Deed of Assignment',
  survey_plan: 'Survey Plan',
  governors_consent: "Governor's Consent",
  receipt: 'Receipt',
  poa: 'Power of Attorney',
};

export const CATEGORY_LABELS: Record<string, string> = {
  identity: 'Identity',
  financial: 'Financial',
  property: 'Property',
  other: 'Other',
};

/** What a queue row is called. Falls back to the raw value rather than an
 * empty cell — a reviewer must always be able to tell rows apart. */
export function describeDocument(item: DocQueueItem): string {
  if (item.source === 'personal') {
    return item.file_name ?? 'Untitled document';
  }
  const type = item.document_type;
  if (!type) return 'Document';
  return DOCUMENT_TYPE_LABELS[type] ?? type.replace(/_/g, ' ');
}

/** Human file size, or null when the table does not record one — only
 * user_documents stores size_bytes; listing_documents has no such column. */
export function formatFileSize(bytes: number | null): string | null {
  if (bytes === null) return null;
  if (bytes < 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** The owner column. A user with no `user_pii` row has no name, and the LEFT
 * JOIN keeps them in the queue on purpose — fall back to the id so the row is
 * still actionable rather than an anonymous dash. */
export function describeOwner(item: DocQueueItem): string {
  if (item.source === 'personal') {
    return item.owner_name ?? item.user_id ?? '—';
  }
  return item.listing_id ?? '—';
}
