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
