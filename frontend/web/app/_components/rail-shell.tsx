'use client';

import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useId, useRef, useState } from 'react';

import { BrandLogo } from './brand-logo';

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * The responsive frame around the admin, seller and realtor sidebars (SCRUM-244).
 *
 * Until this ticket each portal drew a fixed 256px rail with no breakpoint, so
 * on a 375px phone the page itself got ~119px. Now:
 *
 *   - ≥1024px (`lg`): the rail sits in the page exactly as before.
 *   - <1024px: a 64px top bar with a menu button; the SAME `<aside>` slides in
 *     from the left as a drawer over a scrim.
 *
 * One element, not a desktop rail plus a mobile copy: the rail's contents
 * (notification bell, push toggle, account switch) are stateful client
 * components that poll or fetch, and rendering them twice would double that.
 *
 * Closed below `lg` the drawer is `invisible` as well as translated away, which
 * takes it out of the tab order and the accessibility tree without needing a
 * matchMedia listener. The parent must be `flex-col lg:flex-row` so the top bar
 * stacks above the page on small screens.
 *
 * `sticky` is the admin treatment: its pages are long paginated tables, so the
 * desktop rail pins to the viewport instead of stretching with the content.
 */
export function RailShell({
  subtitle,
  sticky = false,
  children,
}: {
  /** Shown beside the logo in the mobile top bar, e.g. "Admin Console". */
  subtitle: string;
  sticky?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const drawerId = useId();
  const drawerRef = useRef<HTMLElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  // Picking a destination navigates; the drawer must not still be covering the
  // page that just loaded. No focus return here — the focus belongs to the new page.
  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    const drawer = drawerRef.current;
    drawer?.querySelector<HTMLElement>(FOCUSABLE)?.focus();

    // The page behind a modal drawer must not scroll under the user's thumb.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        close();
        return;
      }
      // Keep Tab cycling inside the drawer while it is modal.
      if (event.key !== 'Tab' || !drawer) return;
      const items = Array.from(drawer.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, close]);

  // Rotating to landscape on a tablet can cross `lg` with the drawer open;
  // the rail is then inline, so the scroll lock and focus trap must go.
  useEffect(() => {
    if (!open) return;
    const desktop = window.matchMedia('(min-width: 1024px)');
    const onChange = () => desktop.matches && setOpen(false);
    desktop.addEventListener('change', onChange);
    return () => desktop.removeEventListener('change', onChange);
  }, [open]);

  return (
    <>
      <div className="sticky top-0 z-30 flex h-16 flex-none items-center gap-3 border-b border-line bg-surface-card px-4 lg:hidden">
        <button
          ref={triggerRef}
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls={drawerId}
          className="-ml-2 flex h-11 w-11 flex-none items-center justify-center rounded-xl text-ink-700 transition hover:bg-surface-muted"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className="h-6 w-6" aria-hidden>
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <BrandLogo height={24} />
        <span className="truncate text-xs leading-4 text-ink-500">{subtitle}</span>
      </div>

      {open && (
        <>
          <div className="fixed inset-0 z-40 bg-black/40 lg:hidden" onClick={close} aria-hidden />
          {/* Sits in the scrim's uncovered strip to the right of the drawer
              (the drawer is capped at 85vw), so it never collides with the
              bell or logo inside the rail's brand block. A sibling of the
              scrim, not a child: the scrim is aria-hidden. */}
          <button
            type="button"
            onClick={close}
            aria-label="Close menu"
            className="fixed right-2 top-3 z-40 flex h-11 w-11 items-center justify-center rounded-xl text-white lg:hidden"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className="h-6 w-6" aria-hidden>
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </>
      )}

      <aside
        id={drawerId}
        ref={drawerRef}
        aria-label="Menu"
        // `visibility` is transitioned only on CLOSE (so the drawer stays
        // visible while it slides out). On open it must flip instantly: a
        // transitioning hidden→visible is still `hidden` on its first frame,
        // and the focus() in the effect above would be silently ignored.
        className={`fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-none flex-col overflow-y-auto border-r border-line bg-surface-card duration-200 lg:static lg:z-auto lg:w-64 lg:max-w-none lg:translate-x-0 lg:overflow-visible lg:transition-none ${
          open
            ? 'visible translate-x-0 shadow-2xl transition-transform'
            : 'invisible -translate-x-full transition-[transform,visibility] lg:visible'
        } ${sticky ? 'lg:sticky lg:top-0 lg:h-screen lg:self-start' : ''}`}
      >
        {children}
      </aside>
    </>
  );
}
