/**
 * Shared chrome for the onboarding and post-verification flows — SCRUM-184.
 *
 * Measured off the exports in `design/onboarding/`,
 * `design/buyers-after-email-verification/`,
 * `design/sellers-after-email--verification/` and
 * `design/realtors-after-email-verification/`.
 *
 * BOTH width groups (1577 and 1562) are 1:1. The reliable test is that values
 * come out round in each: the content column is exactly 768px in both, the
 * welcome screen's stat tiles are 240px at a 24px gutter (3×240 + 2×24 = 768),
 * and cards, chips and buttons all land on a 16px radius. (Counting decimals is
 * NOT a reliable scale test — see SCRUM-171.)
 *
 * The measured vocabulary, used by every screen in these flows:
 *   column        768px, centred
 *   select card   768×144, 16px radius, 1px SOLID #e5e7eb
 *   icon chip     80×80, 16px radius, `surface-warm`
 *   primary CTA   768×68, 16px radius
 *   disabled CTA  #e5e7eb fill (`line`) — a filled grey, not a faded green
 *
 * ⚠️ Card borders here are SOLID `#e5e7eb`, not the buyer surface's 50%-opacity
 * hairline (SCRUM-169). Measured directly: the border pixel reads #e5e7eb with
 * a single #f2f3f5 antialias step either side. Do not "harmonise" it.
 */

import { CheckIcon } from './icons';

/** 768px centred column — the measured content width of every screen in these flows. */
export function OnboardingShell({
  children,
  className = '',
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <main className="relative min-h-screen bg-white">
      <div className={`mx-auto flex min-h-screen w-full max-w-[816px] flex-col justify-center px-6 py-12 ${className}`}>
        {children}
      </div>
    </main>
  );
}

/** Centred page heading pair. Title 48px bold, subtitle 20px `ink-500`. */
export function OnboardingHeading({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="text-center">
      <h1 className="text-[34px] font-bold leading-[1.15] text-ink-buyer sm:text-[48px]">{title}</h1>
      {subtitle && <p className="mt-3 text-lg leading-7 text-ink-500 sm:text-xl">{subtitle}</p>}
    </div>
  );
}

/**
 * The 144px selection card used by the role picker and the seller's selling
 * authority. Selected state inverts the icon chip to `emerald-deep` and shows a
 * filled check at the trailing edge.
 *
 * Rendered as a real <button> rather than a styled div so it is keyboard
 * reachable and announces its pressed state; the design draws no focus ring,
 * but one is required (WCAG AA) so `focus-visible` gets the same emerald edge
 * the selected state uses.
 */
export function SelectCard({
  Icon,
  label,
  description,
  selected,
  onSelect,
  compact = false,
}: {
  Icon: (props: { className?: string }) => React.ReactElement;
  label: string;
  description: string;
  selected: boolean;
  onSelect: () => void;
  /** Seller authority tiles are half-width and shorter than the role cards. */
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      // NOTE: the background lives ONLY in the selected/unselected branch.
      // A `bg-white` in the base list silently beat `bg-[#f3f5f4]` here — same
      // specificity, and Tailwind emits arbitrary values in a different block,
      // so source order decided it and the selected fill never rendered. Same
      // family as `sm:text-6xl` resetting `leading-` in SCRUM-178.
      className={`flex w-full items-center gap-6 rounded-2xl border px-8 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep ${
        compact ? 'h-[104px]' : 'h-[144px]'
      } ${
        selected
          ? 'border-emerald-deep bg-[#f3f5f4] shadow-sm'
          : 'border-line bg-white hover:border-ink-400'
      }`}
    >
      {!compact && (
        <span
          className={`flex h-20 w-20 flex-none items-center justify-center rounded-2xl transition ${
            selected ? 'bg-emerald-deep text-white' : 'bg-surface-warm text-emerald-deep'
          }`}
        >
          <Icon className="h-8 w-8" />
        </span>
      )}

      <span className="min-w-0 flex-1">
        <span className="block text-[22px] font-bold leading-7 text-ink-buyer">{label}</span>
        <span className="mt-1 block text-base font-semibold leading-6 text-ink-500">
          {description}
        </span>
      </span>

      {/* Reserve the check's footprint always, so selecting does not reflow the row. */}
      <span className="flex h-7 w-7 flex-none items-center justify-center">
        {selected && (
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-deep text-white">
            <CheckIcon className="h-4 w-4" strokeWidth={2.6} />
          </span>
        )}
      </span>
    </button>
  );
}

/**
 * 68px full-width primary action.
 *
 * The disabled state is a FILLED `#e5e7eb` with muted text, exactly as drawn —
 * not the usual `opacity-50` on the green. Every screen in these flows shows
 * the button disabled until its requirements are met, so this is the state a
 * user sees first and it needs to be right.
 */
export function PrimaryButton({
  children,
  disabled,
  onClick,
  type = 'button',
}: {
  children: React.ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  type?: 'button' | 'submit';
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`flex h-[68px] w-full items-center justify-center gap-2 rounded-2xl text-base font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep focus-visible:ring-offset-2 ${
        disabled
          ? 'cursor-not-allowed bg-line text-ink-400'
          : 'bg-emerald-deep text-white hover:brightness-110'
      }`}
    >
      {children}
    </button>
  );
}

/** Secondary, text-only action — the "Skip for now" beside a primary CTA. */
export function GhostButton({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-lg px-4 py-3 text-base font-semibold text-ink-500 transition hover:text-ink-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep disabled:cursor-not-allowed disabled:opacity-50"
    >
      {children}
    </button>
  );
}
