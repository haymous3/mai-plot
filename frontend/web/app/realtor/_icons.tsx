/**
 * Line icons for the realtor portal — SCRUM-204.
 *
 * Same approach as `app/_landing/icons.tsx` and `app/_onboarding/icons.tsx`:
 * hand-rolled inline SVG on one 24×24 stroked frame, no icon dependency. The
 * design draws a Lucide-style set; adding `lucide-react` for a couple of dozen
 * glyphs is not worth the bundle or the supply-chain surface when every other
 * surface in this app already hand-rolls them.
 *
 * Icons inherit colour and size from the caller (`currentColor`, `h-*`/`w-*`),
 * so a caller always sets a size — there is no sensible default.
 */

type IconProps = {
  className?: string;
  /** Stroke weight. 1.8 reads correctly at 20-24px; drop to 1.6 below that. */
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

export function SearchIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </Svg>
  );
}

export function FilterIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 5h18l-7 8v6l-4 2v-8Z" />
    </Svg>
  );
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m6 9 6 6 6-6" />
    </Svg>
  );
}

export function ArrowLeftIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M19 12H5" />
      <path d="m12 19-7-7 7-7" />
    </Svg>
  );
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </Svg>
  );
}

export function MapPinIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M20 10c0 5.5-8 12-8 12s-8-6.5-8-12a8 8 0 0 1 16 0Z" />
      <circle cx="12" cy="10" r="3" />
    </Svg>
  );
}

export function CalendarIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </Svg>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </Svg>
  );
}

export function CheckCircleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M21.5 11.1V12a9.5 9.5 0 1 1-5.6-8.7" />
      <path d="m9 11.5 3 3 9.5-9.5" />
    </Svg>
  );
}

export function AlertCircleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5M12 16.2v.1" />
    </Svg>
  );
}

export function HouseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3.5 10.5 12 4l8.5 6.5V20a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1Z" />
      <path d="M9.5 21v-6h5v6" />
    </Svg>
  );
}

export function ShieldCheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3l7 3v5.5c0 4.4-2.9 8.2-7 9.5-4.1-1.3-7-5.1-7-9.5V6Z" />
      <path d="m9 12 2 2 4-4" />
    </Svg>
  );
}

export function FileTextIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7Z" />
      <path d="M14 3v4h4M9 12h6M9 16h4" />
    </Svg>
  );
}

export function CameraIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 8.5a1 1 0 0 1 1-1h2.5l1.5-2h6l1.5 2H20a1 1 0 0 1 1 1V19a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" />
      <circle cx="12" cy="13" r="3.5" />
    </Svg>
  );
}

export function VideoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="6" width="12" height="12" rx="2" />
      <path d="m15 10.5 6-3.5v10l-6-3.5Z" />
    </Svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m5 12.5 5 5L19 7" />
    </Svg>
  );
}

export function XIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 6l12 12M18 6 6 18" />
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

export function MapIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m9 4-6 3v13l6-3 6 3 6-3V4l-6 3Z" />
      <path d="M9 4v13M15 7v13" />
    </Svg>
  );
}

export function TrendingUpIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m3 17 6-6 4 4 8-8" />
      <path d="M15 7h6v6" />
    </Svg>
  );
}

export function WalletIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v1" />
      <path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3" />
      <path d="M21 10.5h-4a1.5 1.5 0 0 0 0 3h4Z" />
    </Svg>
  );
}

export function BellIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M18 8.5a6 6 0 1 0-12 0c0 5-2 6.5-2 6.5h16s-2-1.5-2-6.5Z" />
      <path d="M13.7 19a2 2 0 0 1-3.4 0" />
    </Svg>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
      <path d="M12 15V4M8 8l4-4 4 4" />
    </Svg>
  );
}

export function ClipboardIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <path d="M9 4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1Z" />
      <path d="M9 11h6M9 15h4" />
    </Svg>
  );
}

export function UserIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-3.3 3.6-6 8-6s8 2.7 8 6" />
    </Svg>
  );
}
