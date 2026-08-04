import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import { Carousel } from './carousel';
import { PropertyActions } from './property-actions';
import { RecordView } from './record-view';
import type {
  DealsResponse,
  FeedResponse,
  ListingDetail,
  ListingDocumentsResponse,
} from '@/lib/api';
import { documentServiceUrl, listingServiceUrl, transactionServiceUrl } from '@/lib/api';
import { BUYER_LOGIN } from '@/lib/buyer-auth';
import { buyerBackendGet } from '@/lib/buyer-server-api';
import { isDealActive } from '@/lib/deal-stage';
import { formatNaira } from '@/lib/format';

export const metadata: Metadata = { title: 'Property · Maiplot' };

const DOC_LABELS: Record<string, string> = {
  c_of_o: 'Certificate of Occupancy (C of O)',
  deed_of_assignment: 'Deed of Assignment',
  survey_plan: 'Survey Plan',
  governors_consent: "Governor's Consent",
  receipt: 'Purchase Receipt',
  poa: 'Power of Attorney',
  other: 'Supporting Document',
};

function daysLeft(iso: string | null): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return ms <= 0 ? 0 : Math.ceil(ms / 86_400_000);
}

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-card border border-line/50 bg-surface-card p-8 ${className}`}>
      {children}
    </section>
  );
}

export default async function ListingDetailPage({ params }: { params: { id: string } }) {
  const [detailRes, docsRes, savedRes, dealsRes] = await Promise.all([
    buyerBackendGet<ListingDetail>(`${listingServiceUrl()}/listings/${params.id}`),
    buyerBackendGet<ListingDocumentsResponse>(
      `${documentServiceUrl()}/listings/${params.id}/documents`,
    ),
    buyerBackendGet<FeedResponse>(`${listingServiceUrl()}/listings/saved`),
    buyerBackendGet<DealsResponse>(`${transactionServiceUrl()}/transactions`),
  ]);

  if (!detailRes.ok) {
    if (detailRes.status === 401) redirect(BUYER_LOGIN);
    if (detailRes.status === 404) notFound();
    throw new Error(`Failed to load listing (${detailRes.code})`);
  }
  const listing = detailRes.data;
  const docs = docsRes.ok ? docsRes.data.documents : [];
  const isSaved = savedRes.ok ? savedRes.data.data.some((i) => i.id === listing.id) : false;
  // An accepted deal on this listing enables "Make a deposit".
  const matchingDeal = (dealsRes.ok ? dealsRes.data.data : []).find(
    (d) => d.listing_id === listing.id && isDealActive(d.stage),
  );
  const deal = matchingDeal
    ? { transactionId: matchingDeal.transaction_id, agreedPriceKobo: matchingDeal.agreed_price_kobo }
    : null;
  const left = daysLeft(listing.urgency_expires_at);
  const isPoa = listing.seller.authority_type === 'power_of_attorney';

  const badges = (
    <>
      {listing.sale_type === 'distress' && (
        <span className="w-fit rounded-full bg-status-urgent px-2.5 py-1 text-xs font-semibold text-white">
          🔥 Distress Sale
        </span>
      )}
      <span className="w-fit rounded-full bg-emerald-deep px-2.5 py-1 text-xs font-semibold text-bone">
        ✓ Verified Documents
      </span>
    </>
  );

  return (
    <main className="mx-auto max-w-6xl px-6 py-6">
      <RecordView
        listing={{
          id: listing.id,
          title: listing.title,
          location: listing.address_text,
          asking_price_kobo: listing.asking_price_kobo,
          sale_type: listing.sale_type,
          thumbnail_url: listing.media[0]?.url ?? null,
        }}
      />
      <Link href="/dashboard" className="text-sm text-ink-500 transition hover:text-ink-900">
        ← Back to listings
      </Link>

      <div className="mt-4">
        <Carousel
          listingId={listing.id}
          images={listing.media.map((m) => m.url)}
          badges={badges}
          daysLeft={left}
          initialSaved={isSaved}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          <Card>
            <h1 className="font-display text-3xl text-ink-900">{listing.title}</h1>
            <p className="mt-1 text-sm text-ink-500">📍 {listing.address_text}</p>
            <p className="mt-4 font-display text-3xl text-emerald-deep">
              {formatNaira(listing.asking_price_kobo)}
            </p>
            <div className="mt-5 grid grid-cols-2 gap-4 border-t border-line pt-4 sm:grid-cols-3">
              <div>
                <p className="text-xs text-ink-500">Property Type</p>
                <p className="mt-0.5 font-medium capitalize text-ink-900">{listing.property_type}</p>
              </div>
              {listing.size_sqm && (
                <div>
                  <p className="text-xs text-ink-500">Size</p>
                  <p className="mt-0.5 font-medium text-ink-900">
                    ⤢ {Number(listing.size_sqm).toLocaleString()} sqm
                  </p>
                </div>
              )}
              <div>
                <p className="text-xs text-ink-500">Views</p>
                <p className="mt-0.5 font-medium text-ink-900">{listing.view_count}</p>
              </div>
            </div>
          </Card>

          {listing.description && (
            <Card>
              <h2 className="font-display text-xl text-ink-900">Description</h2>
              <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink-700">
                {listing.description}
              </p>
            </Card>
          )}

          <Card>
            <h2 className="flex items-center gap-2 font-display text-xl text-ink-900">
              📄 Document Verification
            </h2>
            <p className="text-xs text-ink-500">Reviewed by our legal team</p>
            <div className="mt-4 space-y-2">
              {docs.length === 0 ? (
                <p className="text-sm text-ink-400">No documents published yet.</p>
              ) : (
                docs.map((d, n) => {
                  const verified = d.verification_status === 'verified';
                  return (
                    <div
                      key={n}
                      className="flex items-center justify-between rounded-lg bg-bone px-4 py-3"
                    >
                      <span className="flex items-center gap-2 text-sm text-ink-900">
                        <span className={verified ? 'text-emerald-deep' : 'text-ink-300'}>
                          {verified ? '✓' : '○'}
                        </span>
                        {DOC_LABELS[d.document_type] ?? d.document_type}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
                          verified
                            ? 'bg-emerald-deep/10 text-emerald-deep'
                            : 'bg-ink-300/20 text-ink-500'
                        }`}
                      >
                        {d.verification_status.replace('_', ' ')}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </Card>

          <Card>
            <h2 className="font-display text-xl text-ink-900">Location</h2>
            <p className="mt-2 text-sm text-ink-500">{listing.address_text}</p>
            <a
              href={`https://www.google.com/maps/search/?api=1&query=${listing.location.lat},${listing.location.lng}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-block rounded-lg border border-ink-300/50 px-4 py-2.5 text-sm font-medium text-emerald-deep transition hover:border-emerald-accent"
            >
              🗺 View Full Map
            </a>
          </Card>
        </div>

        <aside className="space-y-4">
          <Card className="!p-5">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-deep text-sm font-semibold text-bone">
                {(listing.seller.poa_owner_name ?? 'S')[0].toUpperCase()}
              </span>
              <div>
                <p className="font-medium text-ink-900">
                  {listing.seller.poa_owner_name ?? 'Property Seller'}
                </p>
                <p className="text-xs text-ink-500">{isPoa ? 'Power of Attorney' : 'Direct Owner'}</p>
              </div>
            </div>
            {listing.seller.trust_score !== null && (
              <div className="mt-4">
                <div className="flex justify-between text-xs text-ink-500">
                  <span>Trust Score</span>
                  <span>{listing.seller.trust_score}/100</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-ink-300/30">
                  <div
                    className="h-1.5 rounded-full bg-emerald-deep"
                    style={{ width: `${listing.seller.trust_score}%` }}
                  />
                </div>
              </div>
            )}
            <p className="mt-4 flex items-start gap-2 rounded-lg bg-bone px-3 py-2 text-xs text-ink-600">
              🛡 This property is listed by a verified {isPoa ? 'representative' : 'owner'}.
            </p>
          </Card>

          <div className="rounded-2xl bg-emerald-deep p-5 text-bone">
            <p className="flex items-center gap-2 font-semibold">🔒 Trust &amp; Safety</p>
            <ul className="mt-3 space-y-1.5 text-sm text-bone/85">
              <li>✓ Passed initial verification checks</li>
              <li>✓ Secured through escrow</li>
              <li>✓ Legal team reviewed</li>
            </ul>
          </div>

          {listing.loan_eligibility_kobo !== null && (
            <Card className="!p-5">
              <p className="flex items-center gap-2 font-semibold text-ink-900">💳 Loan Eligibility</p>
              <p className="mt-2 text-sm text-ink-500">
                You may finance up to{' '}
                <span className="font-semibold text-emerald-deep">
                  {formatNaira(listing.loan_eligibility_kobo)}
                </span>{' '}
                (50% of the asking price) on this property.
              </p>
            </Card>
          )}

          <Card className="!p-5">
            <p className="flex items-center gap-2 font-semibold text-ink-900">📈 Market Insight</p>
            <p className="mt-2 text-sm text-ink-500">
              This listing has {listing.interest_count} interested{' '}
              {listing.interest_count === 1 ? 'buyer' : 'buyers'} and {listing.view_count} views.
            </p>
          </Card>
        </aside>
      </div>

      <PropertyActions
        listingId={listing.id}
        askingPriceKobo={listing.asking_price_kobo}
        deal={deal}
      />
    </main>
  );
}
