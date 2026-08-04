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
    // Page background is `surface-page` (#f9fafb), not `bone` — measured on the
    // buyer dashboard export (SCRUM-166). `bone` (#f6f4ee) is the warm brand
    // cream, used for panels, not as the app canvas.
    <div className="min-h-screen bg-surface-page">
      <OfflineBanner />
      <BuyerNav />
      {children}
    </div>
  );
}
