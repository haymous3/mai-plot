import type { Metadata } from 'next';

import { ComingSoon } from '../coming-soon';

export const metadata: Metadata = { title: 'Assigned Inspections · Maiplot Realtor' };

export default function RealtorInspectionsPage() {
  return (
    <ComingSoon
      title="Assigned Inspections"
      subtitle="Accept assignments and schedule your visits"
      note="Your assigned inspections list is landing next."
    />
  );
}
