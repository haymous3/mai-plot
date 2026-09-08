'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';

import { REVEAL_ROOT_MARGIN } from '@/lib/motion';

/**
 * Reveals its content as it scrolls into view (SCRUM-216).
 *
 * The only JavaScript in the landing page's motion: everything else is a CSS
 * transition declared in `globals.css`. This component's whole job is to flip
 * one data attribute from `out` to `in` when the element first enters the
 * viewport.
 *
 * TWO SHAPES, ONE COMPONENT:
 *   <Reveal>            one block moves as a unit — a heading, a panel.
 *   <Reveal stagger>    the DIRECT CHILDREN arrive in sequence.
 *
 * `stagger` exists so this component can BE the grid rather than wrap it —
 * pass the grid's own className through and the markup gains no extra node,
 * so no layout can shift. The per-child delays come from `:nth-child` rules in
 * globals.css, not from inline styles, for the same reason.
 *
 * ⚠️ IT REVEALS ONCE AND STOPS. The observer disconnects on the first
 * intersection, so scrolling back up does not re-hide and replay. A section
 * that re-animates every time it passes the fold is the thing that makes a
 * page feel cheap, and it fights anyone re-reading it.
 *
 * `as` keeps list semantics intact: staggering the items of a `<ul>` means
 * this component has to BE the `<ul>`, because the CSS targets direct
 * children. Wrapping the list in a div instead would put the div between them
 * and stagger nothing.
 *
 * ⚠️ THE HIDDEN STATE IS NOT THIS COMPONENT'S DOING. `data-reveal="out"` only
 * hides anything beneath `.motion-ready`, a class no server render emits — see
 * the safety note in globals.css. If this component never mounts, its content
 * stays visible.
 */
export function Reveal({
  children,
  className,
  stagger = false,
  as: Tag = 'div',
  id,
}: {
  children: ReactNode;
  className?: string;
  /** Sequence the direct children instead of moving the block as one. */
  stagger?: boolean;
  /** The element to render. Use the real list tag when staggering list items. */
  as?: 'div' | 'ul' | 'ol' | 'dl';
  id?: string;
}) {
  const ref = useRef<HTMLElement | null>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Old browsers, and any test environment without the API: show the content
    // rather than leaving it stuck at `out` forever.
    if (typeof IntersectionObserver === 'undefined') {
      setShown(true);
      return;
    }

    // Already in view on mount — above-the-fold content, or a reload partway
    // down the page. The observer fires immediately for this case too, but
    // checking first avoids a frame of hidden content on a deep reload.
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setShown(true);
            observer.disconnect();
            return;
          }
        }
      },
      { rootMargin: REVEAL_ROOT_MARGIN, threshold: 0.05 },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const state = shown ? 'in' : 'out';

  return (
    <Tag
      // A callback ref rather than the object: one `HTMLElement` ref is
      // assignable to every tag `as` allows, so no cast per element type.
      ref={(node: HTMLElement | null) => {
        ref.current = node;
      }}
      id={id}
      className={className}
      {...(stagger ? { 'data-reveal-group': state } : { 'data-reveal': state })}
    >
      {children}
    </Tag>
  );
}
