/**
 * Line icons for the public landing page — SCRUM-178.
 *
 * The design draws a Lucide-style 24px stroked set. We do NOT add
 * `lucide-react` for it: the app hand-rolls inline SVG everywhere else
 * (`verify-otp-client.tsx`, `admin-nav.tsx`, `notification-bell.tsx`), and a
 * runtime dependency for ~14 glyphs on one marketing page is not worth the
 * bundle or the supply-chain surface.
 *
 * All icons share one 24×24 stroked frame so they line up optically and inherit
 * colour and size from the caller (`currentColor`, `h-*`/`w-*`).
 */

type IconProps = {
  /** Tailwind size classes. Callers always set this — there is no sensible default size. */
  className?: string;
  /** Stroke weight. 1.8 reads correctly at 20-24px; drop to 1.6 for smaller glyphs. */
  strokeWidth?: number;
};

function Svg({
  className,
  strokeWidth = 1.8,
  children,
}: IconProps & { children: React.ReactNode }) {
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

export function HouseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8" />
    </Svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.9-3.9" />
    </Svg>
  );
}

export function CheckCircleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12.2 2.4 2.4 4.6-5" />
    </Svg>
  );
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 12h15" />
      <path d="m13 6 6 6-6 6" />
    </Svg>
  );
}

export function MapPinIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11Z" />
      <circle cx="12" cy="10" r="2.5" />
    </Svg>
  );
}

export function FileTextIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6" />
      <path d="M9 17h4" />
    </Svg>
  );
}

export function EyeIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
    </Svg>
  );
}

export function LockIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
    </Svg>
  );
}

export function BanknoteIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="2.5" y="6" width="19" height="12" rx="2" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M6 10v4M18 10v4" />
    </Svg>
  );
}

export function ShieldIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 21s7-3.2 7-9V6l-7-3-7 3v6c0 5.8 7 9 7 9Z" />
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

/** Floor-area marker — the design pairs this with the `size_sqm` figure. */
export function AreaIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </Svg>
  );
}
