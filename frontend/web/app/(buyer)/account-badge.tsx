import Link from 'next/link';

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

/**
 * Header account photo (SCRUM-248). Until SCRUM-248 this was the Account
 * dropdown (SCRUM-95/237); its links — My Offers, My Wallet, Settings, the
 * seller switch and Sign Out — now live in the buyer rail, so what is left is
 * who is signed in, linking to their Settings profile.
 *
 * The photo URL is a short-lived pre-signed link minted by the server render
 * (SCRUM-240); initials when no photo is set.
 */
export function AccountBadge({ avatarUrl, name }: { avatarUrl: string | null; name: string }) {
  return (
    <Link
      href="/settings"
      aria-label="Account settings"
      className="flex items-center gap-2 rounded-full py-1 pl-1 pr-1 text-bone/90 transition hover:bg-white/10 sm:pr-3"
    >
      <span className="flex h-7 w-7 flex-none items-center justify-center overflow-hidden rounded-full bg-emerald-deep text-xs font-semibold text-white">
        {avatarUrl ? (
          // Pre-signed S3 URL — not next/image (see AvatarField in settings).
          // eslint-disable-next-line @next/next/no-img-element
          <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          initialsOf(name) || '👤'
        )}
      </span>
      <span className="hidden text-left text-xs leading-tight sm:block">
        <span className="block font-medium">Account</span>
        <span className="block text-bone/60">Buyer</span>
      </span>
    </Link>
  );
}
