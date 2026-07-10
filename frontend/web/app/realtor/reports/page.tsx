import type { Metadata } from 'next';

import { ComingSoon } from '../coming-soon';

export const metadata: Metadata = { title: 'Reports Submitted · Maiplot Realtor' };

export default function RealtorReportsPage() {
  return (
    <ComingSoon
      title="Reports Submitted"
      subtitle="Your inspection report history"
      note="Your submitted reports and their review status are landing soon."
    />
  );
}
