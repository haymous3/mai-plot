/**
 * Presentation helpers for the seller notification inbox (SCRUM-194).
 *
 * The category a notification belongs to is decided SERVER-side (see
 * notification-service `app/services/categories.py`) and drives the tabs. What
 * lives here is only how a row LOOKS: its icon and accent.
 */

/** The inbox tabs. `all` is the absence of a filter, not a server value.
 *
 * ⚠️ There is no "messages" tab. This product has no messaging feature — no
 * service, no endpoints — so the design's Messages tab was dropped rather than
 * shipped as a control that could never fill.
 *
 * ⚠️ "Bids" is the design's word; this product has OFFERS (§8 rule 4). The
 * label follows the design, the data behind it is offers.
 */
export const INBOX_TABS = ['all', 'deposits', 'bids', 'documents', 'system'] as const;
export type InboxTab = (typeof INBOX_TABS)[number];

export const TAB_LABELS: Record<InboxTab, string> = {
  all: 'All',
  deposits: 'Deposits',
  bids: 'Bids',
  documents: 'Documents',
  system: 'System',
};

export function isInboxTab(value: string | undefined): value is InboxTab {
  return value !== undefined && (INBOX_TABS as readonly string[]).includes(value);
}

/** Narrow an untrusted query-string value to a tab, defaulting to All. */
export function parseTab(value: string | undefined): InboxTab {
  return isInboxTab(value) ? value : 'all';
}

type Accent = 'money' | 'offer' | 'document' | 'system';

/** Which visual family a row belongs to, from its server-side `type`.
 *
 * Deliberately mirrors the server's category mapping rather than re-deriving a
 * different grouping: a row that sits under Documents must not be painted as
 * money. An unknown type falls back to `system`, matching the server's
 * catch-all, so a newly shipped notification still renders sensibly.
 */
export function accentFor(notificationType: string): Accent {
  if (notificationType.startsWith('offer_')) return 'offer';
  if (notificationType.startsWith('document_') || notificationType.startsWith('poa_')) {
    return 'document';
  }
  if (
    notificationType.startsWith('deposit_') ||
    notificationType === 'loan_disbursed' ||
    notificationType === 'title_released'
  ) {
    return 'money';
  }
  return 'system';
}

/** Tailwind classes for a row's icon tile, keyed by accent.
 *
 * Spelled out as whole class strings rather than composed at runtime —
 * Tailwind only emits classes it can see literally in the source, and a
 * template-built name compiles to nothing at all.
 *
 * ⚠️ Every colour here is one this project's palette actually emits, checked
 * against the BUILT CSS. The first draft used `sky` and `rose`, which are not
 * in the theme at all: those four classes compiled to nothing and the document
 * and system tiles would have rendered untinted, with no error anywhere.
 * `blue` and `red` are the nearest families that do exist.
 */
export const ACCENT_TILE: Record<Accent, string> = {
  money: 'bg-emerald-deep/10 text-emerald-deep',
  offer: 'bg-amber-100 text-amber-700',
  document: 'bg-blue-100 text-blue-700',
  system: 'bg-red-100 text-red-600',
};

/** A readable heading when a notification has no title of its own.
 *
 * Every producer sets one today, but `notifications.title` is nullable, so the
 * fallback keeps a row identifiable instead of rendering a blank line.
 */
export function headingFor(item: { title: string | null; type: string }): string {
  if (item.title && item.title.trim()) return item.title;
  return item.type.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}
