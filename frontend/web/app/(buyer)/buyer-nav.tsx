import { AvatarMenu } from './avatar-menu';
import { NotificationBell } from './notification-bell';
import { BrandLogo } from '@/app/_components/brand-logo';
import { authServiceUrl } from '@/lib/api';
import { buyerBackendGet } from '@/lib/buyer-server-api';
import type { Account } from '@/lib/settings';

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/**
 * Shared buyer header (SCRUM-95): brand · greeting · notification bell ·
 * account menu. Rendered on every buyer page via the (buyer) layout.
 *
 * Measured against the design (SCRUM-166): 72px tall, 44px inline padding,
 * `#144735` fill and a 1px `#e5e7eb` bottom rule. The fill is `brand-header`,
 * not `emerald-deep` — the buyer top bar is the one place the design uses a
 * lighter green than the `#0f3d2e` primary. Seller and realtor have a sidebar
 * instead, so this token is used nowhere else.
 *
 * The greeting is centred absolutely rather than by `justify-between`, which
 * only centres it when both flanking groups happen to be the same width.
 */
export async function BuyerNav() {
  // SCRUM-240: the account photo in the header. Read per render because
  // `avatar_url` is a 15-minute pre-signed URL, never a durable link. A failed
  // read is not worth breaking the header over — the menu falls back to the
  // generic glyph.
  const me = await buyerBackendGet<Account>(`${authServiceUrl()}/auth/me`);
  const account = me.ok ? me.data : null;

  return (
    <header className="relative flex h-18 items-center justify-between border-b border-line bg-brand-header px-11">
      {/* The design was inconsistent here — "MaiHome" in 5 buyer export
          frames, "Maiplot" in 2. Product owner chose "Maihomme" (SCRUM-173),
          confirmed verbatim, and SCRUM-186 swept that name across every
          consumer-facing surface. Only "Maiplot Technologies Ltd" (the legal
          entity, in the landing footer) and internal identifiers — the
          Postgres user/database, container and package names, the `mai-plot`
          repo — deliberately keep the old name. SCRUM-230 replaced the typed
          wordmark with the designer's logo; the name it spells is the same. */}
      {/* SCRUM-238: the logo goes to the landing page, not the dashboard —
          the Account menu is the way back to the dashboard. */}
      <BrandLogo tone="dark" height={28} priority />
      <p className="pointer-events-none absolute left-1/2 hidden -translate-x-1/2 text-sm text-bone/80 sm:block">
        {greeting()}
      </p>
      <div className="flex items-center gap-1.5">
        <NotificationBell />
        <AvatarMenu avatarUrl={account?.avatar_url ?? null} name={account?.full_name ?? ''} />
      </div>
    </header>
  );
}
