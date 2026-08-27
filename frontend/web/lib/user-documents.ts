/**
 * Shared types for My Documents (SCRUM-188), mirroring document-service
 * `/documents/personal`.
 */

export const DOCUMENT_CATEGORIES = ['identity', 'financial', 'property', 'other'] as const;
export type DocumentCategory = (typeof DOCUMENT_CATEGORIES)[number];

export const CATEGORY_LABELS: Record<DocumentCategory, string> = {
  identity: 'Identity',
  financial: 'Financial',
  property: 'Property',
  other: 'Other',
};

/**
 * ⚠️ `failed` is what the design's "Rejected" pill labels. The three document
 * tables share one status vocabulary rather than each inventing its own — see
 * document-service migration 0003 — so the rename happens here, in the view.
 */
export const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  verified: 'Verified',
  failed: 'Rejected',
  under_review: 'In review',
};

export type UserDocument = {
  id: string;
  category: DocumentCategory;
  file_name: string;
  size_bytes: number;
  content_type: string;
  verification_status: string;
  verification_notes: string | null;
  created_at: string;
};

export type UserDocuments = {
  items: UserDocument[];
  /** Every key is always present, including zeroes — the design draws them. */
  category_counts: Record<string, number>;
  status_counts: Record<string, number>;
  total: number;
};

/** "2.4 MB", matching the design's per-row metadata line. */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const;

/**
 * "15 Mar 2026".
 *
 * ⚠️ Deliberately NOT `toLocaleDateString()`. This component is
 * server-rendered and then hydrated, and the two runtimes do not share a
 * locale: Node produced "15/03/2026" while the browser produced "3/15/2026",
 * which React reports as a hydration mismatch and repaints the whole document.
 * Any locale-dependent formatting in an SSR'd component has this problem.
 *
 * The format also diverges from the design's "3/15/2024" on purpose. That is
 * US M/D/Y; Nigeria writes D/M/Y, so a numeric date is genuinely ambiguous to
 * this product's users. A named month cannot be misread either way.
 */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** "PDF" / "JPG" / "PNG" for the row's type chip. */
export function formatKind(contentType: string): string {
  if (contentType === 'application/pdf') return 'PDF';
  if (contentType === 'image/jpeg') return 'JPG';
  if (contentType === 'image/png') return 'PNG';
  return 'FILE';
}
