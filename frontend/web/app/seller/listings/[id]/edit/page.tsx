import type { Metadata } from 'next';
import { notFound, redirect } from 'next/navigation';

import { EditListingForm } from './edit-listing-form';
import type { ListingDetail } from '@/lib/api';
import { listingServiceUrl } from '@/lib/api';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Edit Listing · Maihomme Seller' };

export default async function EditListingPage({ params }: { params: { id: string } }) {
  const result = await sessionBackendGet<ListingDetail>(
    `${listingServiceUrl()}/listings/${encodeURIComponent(params.id)}`,
  );
  if (!result.ok) {
    if (result.status === 401) redirect(`${SESSION_LOGIN}?role=seller`);
    notFound();
  }
  const l = result.data;

  return (
    <main className="px-8 py-8">
      <EditListingForm
        listing={{
          id: l.id,
          title: l.title,
          description: l.description,
          asking_price_kobo: l.asking_price_kobo,
          sale_type: l.sale_type,
          urgency_tag: l.urgency_tag,
        }}
      />
    </main>
  );
}
