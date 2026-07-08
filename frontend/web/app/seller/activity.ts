/** Derives a "Recent Activity" feed for the seller Overview (SCRUM-98) by merging
 * recent offers, sales, and documents — there is no dedicated activity source, so
 * these are folded together and sorted newest-first. */
import type { SellerDeal, SellerDocument, SellerOffer } from '@/lib/api';
import { DOCUMENT_TYPE_LABELS } from '@/lib/api';
import { formatNaira } from '@/lib/format';
import { sellerStageLabel } from '@/lib/seller-deal-stage';

export interface Activity {
  icon: string;
  title: string;
  detail: string;
  ts: number;
}

const DOC_ACTIVITY: Record<string, { icon: string; title: string }> = {
  verified: { icon: '✓', title: 'Document approved' },
  failed: { icon: '!', title: 'Document requires attention' },
  pending: { icon: '◷', title: 'Document under review' },
  under_review: { icon: '◷', title: 'Document under review' },
};

export function buildActivity(
  offers: SellerOffer[],
  sales: SellerDeal[],
  documents: SellerDocument[],
  limit = 6,
): Activity[] {
  const items: Activity[] = [];

  for (const o of offers) {
    items.push({
      icon: '🤝',
      title: o.status === 'countered' ? 'Offer countered' : 'New offer received',
      detail: `${formatNaira(o.offered_price_kobo)} offer on ${o.property_title}`,
      ts: Date.parse(o.created_at),
    });
  }
  for (const s of sales) {
    items.push({
      icon: '📈',
      title: `Deal ${sellerStageLabel(s.stage).toLowerCase()}`,
      detail: `${s.property_title ?? 'Property'} · ${formatNaira(s.agreed_price_kobo)}`,
      ts: Date.parse(s.created_at),
    });
  }
  for (const d of documents) {
    const a = DOC_ACTIVITY[d.verification_status];
    if (!a) continue;
    items.push({
      icon: a.icon,
      title: a.title,
      detail: `${DOCUMENT_TYPE_LABELS[d.document_type] ?? d.document_type} · ${d.property_title ?? 'Property'}`,
      ts: Date.parse(d.created_at),
    });
  }

  return items
    .filter((i) => Number.isFinite(i.ts))
    .sort((a, b) => b.ts - a.ts)
    .slice(0, limit);
}

export function timeAgo(ts: number): string {
  const mins = Math.round((Date.now() - ts) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs === 1 ? '' : 's'} ago`;
  const days = Math.round(hrs / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}
