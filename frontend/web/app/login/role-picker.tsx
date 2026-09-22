import Link from 'next/link';

import { BuildingIcon, HouseIcon, UserCircleIcon } from '../_onboarding/icons';
import { ArrowRightIcon } from '../_landing/icons';

/**
 * Sign-in role picker — SCRUM-235.
 *
 * `/login` with no `?role=` used to default silently to BUYER, which asks for
 * an email. A realtor arriving from anywhere but the two `?role=realtor` links
 * (nav, realtor band) therefore met a form their registration number could
 * not satisfy (SCRUM-207) and no way to find the right one. This screen is
 * that way.
 *
 * ONE CLICK, NO CONTINUE BUTTON. The onboarding role picker is select-then-
 * continue because a registration hangs several steps off the choice; here
 * the choice IS the whole step, so each card is a plain link to the variant
 * of /login that already renders the right form. No state, no client
 * component — a server component with three anchors.
 *
 * Visual vocabulary is the onboarding role card (`app/_onboarding/ui.tsx`,
 * measured from the exports: 16px radius, 1px `line` border, `surface-warm`
 * icon chip, `emerald-deep` glyph) at the compact 104px height, because the
 * sign-in column is `max-w-sm` and the 144px card with its 80px chip needs
 * the 768px onboarding column to breathe. Nothing here is a new pattern.
 *
 * Copy is sign-in framing, not the onboarding benefits copy: the useful fact
 * at this moment is what each account signs in WITH.
 */
const ROLES = [
  {
    role: 'buyer',
    Icon: UserCircleIcon,
    label: 'Buyer / Investor',
    hint: 'Sign in with your email',
  },
  {
    role: 'seller',
    Icon: HouseIcon,
    label: 'Property Seller',
    hint: 'Sign in with your email',
  },
  {
    role: 'realtor',
    Icon: BuildingIcon,
    label: 'Realtor / Agent',
    hint: 'Sign in with your Maihomme registration number',
  },
] as const;

export function RolePicker() {
  return (
    <ul className="flex flex-col gap-4">
      {ROLES.map(({ role, Icon, label, hint }) => (
        <li key={role}>
          <Link
            href={`/login?role=${role}`}
            className="group flex h-[104px] w-full items-center gap-5 rounded-2xl border border-line bg-white px-6 transition hover:border-emerald-deep hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep"
          >
            <span className="flex h-14 w-14 flex-none items-center justify-center rounded-xl bg-surface-warm text-emerald-deep">
              <Icon className="h-7 w-7" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-base font-semibold leading-6 text-ink-900">{label}</span>
              <span className="mt-0.5 block text-sm leading-5 text-ink-500">{hint}</span>
            </span>
            <ArrowRightIcon className="h-5 w-5 flex-none text-ink-300 transition group-hover:translate-x-0.5 group-hover:text-emerald-deep motion-reduce:transform-none" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
