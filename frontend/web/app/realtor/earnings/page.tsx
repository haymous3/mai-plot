import type { Metadata } from 'next';

import { ComingSoon } from '../coming-soon';

export const metadata: Metadata = { title: 'Earnings · Maiplot Realtor' };

export default function RealtorEarningsPage() {
  return (
    <ComingSoon
      title="Earnings"
      subtitle="Your commission balance and payout history"
      note="Your earnings breakdown and transaction history are landing soon."
    />
  );
}
