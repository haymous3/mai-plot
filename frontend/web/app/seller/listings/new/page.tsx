import type { Metadata } from 'next';

import { CreateListingWizard } from './create-wizard';

export const metadata: Metadata = { title: 'Create Listing · Maiplot Seller' };

export default function NewListingPage() {
  return (
    <main className="px-8 py-8">
      <CreateListingWizard />
    </main>
  );
}
