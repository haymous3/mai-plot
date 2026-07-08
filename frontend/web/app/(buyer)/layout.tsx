import { redirect } from 'next/navigation';

import { BuyerNav } from './buyer-nav';
import { OfflineBanner } from './offline-banner';
import { BUYER_LOGIN } from '@/lib/buyer-auth';
import { buyerAccessToken } from '@/lib/buyer-server-api';

/**
 * Buyer route-group shell (SCRUM-94). Gates every buyer page on a buyer session
 * cookie — no token redirects to the login. The chrome is deliberately minimal
 * pending the buyer-dashboard Figma.
 */
export default function BuyerLayout({ children }: { children: React.ReactNode }) {
  if (!buyerAccessToken()) redirect(BUYER_LOGIN);

  return (
    <div className="min-h-screen bg-bone">
      <OfflineBanner />
      <BuyerNav />
      {children}
    </div>
  );
}
