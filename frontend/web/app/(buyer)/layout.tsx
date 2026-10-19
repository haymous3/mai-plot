import { redirect } from 'next/navigation';

import { BuyerNav } from './buyer-nav';
import { BuyerRail } from './buyer-rail';
import { OfflineBanner } from './offline-banner';
import { RailDrawerProvider } from '@/app/_components/rail-shell';
import { BUYER_LOGIN } from '@/lib/buyer-auth';
import { buyerAccessToken } from '@/lib/buyer-server-api';

/**
 * Buyer route-group shell (SCRUM-94). Gates every buyer page on a buyer session
 * cookie — no token redirects to the login.
 *
 * SCRUM-248: green top bar across the full width, then the buyer rail beside
 * the page from `lg` up. Below `lg` the rail is a drawer opened from the ☰ in
 * the top bar — the provider is what connects that button to the rail.
 */
export default function BuyerLayout({ children }: { children: React.ReactNode }) {
  if (!buyerAccessToken()) redirect(BUYER_LOGIN);

  return (
    // Page background is `surface-page` (#f9fafb), not `bone` — measured on the
    // buyer dashboard export (SCRUM-166). `bone` (#f6f4ee) is the warm brand
    // cream, used for panels, not as the app canvas.
    <RailDrawerProvider>
      <div className="flex min-h-screen flex-col bg-surface-page">
        <OfflineBanner />
        <BuyerNav />
        <div className="flex flex-1">
          <BuyerRail />
          {/* min-w-0 lets wide children shrink instead of pushing the page
              past the viewport beside a 256px rail. `clip`, NOT `hidden`:
              overflow-x:hidden makes this a scroll container and silently
              kills the listing page's `sticky bottom-0` offer bar. */}
          <div className="min-w-0 flex-1 overflow-x-clip">{children}</div>
        </div>
      </div>
    </RailDrawerProvider>
  );
}
