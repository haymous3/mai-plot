import type { Metadata } from 'next';

import { CreateListingWizard } from './create-wizard';
import type { SellerPoaStatus } from '@/lib/api';
import { authServiceUrl } from '@/lib/api';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Create Listing · Maihomme Seller' };

export default async function NewListingPage() {
  // The seller's REAL authority, read server-side (SCRUM-199).
  //
  // The wizard's Authority step used to be a free choice that went nowhere —
  // it was never sent with the listing, and the authority that actually governs
  // publishing lives on the account (`users.seller_authority_type`, declared at
  // onboarding). Passing the account state in lets the step reflect the truth
  // and lets a PoA seller upload the document the step now asks for.
  //
  // Optional: a failed read degrades to the old free-choice behaviour rather
  // than blocking listing creation, which has nothing to do with PoA.
  const poaRes = await sessionBackendGet<SellerPoaStatus>(
    `${authServiceUrl()}/auth/seller/poa-status`,
  );

  return (
    <main className="px-8 py-8">
      <CreateListingWizard poa={poaRes.ok ? poaRes.data : null} />
    </main>
  );
}
