/**
 * Line icons for the onboarding and post-verification flows — SCRUM-184.
 *
 * Hand-rolled inline SVG, matching what the rest of the app already does
 * (`verify-otp-client.tsx`, `admin-nav.tsx`, `_landing/icons.tsx`). A few
 * glyphs overlap with the landing set; they are deliberately duplicated rather
 * than shared, so the marketing page and the auth funnel stay independent —
 * neither should be able to break the other by restyling an icon.
 */

type IconProps = {
  className?: string;
  strokeWidth?: number;
};

function Svg({ className, strokeWidth = 1.8, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {children}
    </svg>
  );
}

/** Carousel slide 1, and the Property Seller role. */
export function HouseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8" />
    </Svg>
  );
}

/** Carousel slide 2 — verified documents. */
export function ShieldCheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 21s7-3.2 7-9V6l-7-3-7 3v6c0 5.8 7 9 7 9Z" />
      <path d="m9 11.8 2.1 2.1L15 10" />
    </Svg>
  );
}

/** Carousel slide 3 — financing. */
export function BanknoteIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="2.5" y="6" width="19" height="12" rx="2" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M6 10.5v3M18 10.5v3" />
    </Svg>
  );
}

/** Buyer / Investor role. */
export function UserCircleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="10" r="2.6" />
      <path d="M6.6 18.4a6 6 0 0 1 10.8 0" />
    </Svg>
  );
}

/** Realtor / Agent role. */
export function BuildingIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16" />
      <path d="M15 9h2a2 2 0 0 1 2 2v10" />
      <path d="M8.5 7h3M8.5 11h3M8.5 15h3" />
      <path d="M3 21h18" />
    </Svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </Svg>
  );
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m9 5 7 7-7 7" />
    </Svg>
  );
}
