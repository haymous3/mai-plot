import type { Config } from 'tailwindcss';

/**
 * Token values are measured from the Figma exports, not chosen by eye.
 * Source of truth: docs/design-spec.md (SCRUM-163), which cites the file and
 * pixel coordinates behind every value here.
 *
 * The design contains two palettes — buyer was drawn against a different set
 * than seller and realtor. Per product decision we standardise on the
 * seller/realtor values: they are stock Tailwind, they cover two of three
 * surfaces, and buyer is already scheduled for rework in SCRUM-166/167.
 *
 * Class names are deliberately left unchanged. The values were wrong, not the
 * names, so remapping fixes ~1000 usages without touching a single component.
 */
const config: Config = {
  /**
   * ⚠️ `lib/` is in this list on purpose (added SCRUM-204).
   *
   * Several lib modules hold Tailwind class strings that components render
   * verbatim — `realtor-inspection.ts`'s status pills, `notification-inbox.ts`'s
   * channel badges. Tailwind only emits a class it can SEE in a scanned file,
   * so a class that exists nowhere but `lib/` compiles to nothing and the
   * element silently renders unstyled.
   *
   * That was already true before this ticket; it just hadn't bitten yet,
   * because every such class happened to also appear somewhere under `app/`.
   * The SCRUM-204 status pills were the first to be defined only in lib, and
   * `bg-pending-100` / `bg-scheduled-100` / `bg-done-100` were dropped from the
   * bundle until this glob was widened.
   *
   * Fourth instance of the silent-no-op-class family (`ink-400`, `h-4.5`,
   * `sm:text-6xl`) — verify against the BUILT CSS, never against the source.
   */
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['var(--font-display)', 'ui-serif', 'Georgia', 'serif'],
      },
      colors: {
        emerald: {
          // Primary brand green. Measured on all three surfaces — buyer 1.86%,
          // seller 1.75%, realtor 1.01%. Also the colour of completed wizard
          // steps, selected chips and verified ticks (confirmed: the financing
          // and create-listing screens contain no other green).
          deep: '#0f3d2e',

          // UNVERIFIED. 86 of its 115 usages are `hover:` or `focus:`, and no
          // export captures a hover or focus state — so this value was invented
          // when the screens were built, not taken from the design.
          // Left as-is deliberately: swapping one unverified value for another
          // is churn. SCRUM-165 replaces it with the real value from Figma.
          accent: '#1f7a5a',
        },

        // Buyer header bar only (7.94% of that screen). Does not appear on
        // seller or realtor, which use a sidebar rather than a top bar.
        brand: {
          header: '#144735',
        },

        bone: '#f6f4ee',

        /**
         * Neutral ramp. 900/500/300 are measured; 800/700/600/400 are
         * interpolated from Tailwind's gray scale, which the design otherwise
         * matches exactly.
         *
         * 600 and 400 are NEW. They were referenced 58 times across the app but
         * never defined, so Tailwind emitted nothing and those elements silently
         * inherited their parent colour. Defining them fixes that.
         */
        ink: {
          900: '#101828', // measured — primary text on SELLER and REALTOR
          800: '#1e2939', // interpolated
          700: '#364153', // interpolated
          600: '#4a5565', // interpolated — was undefined, 41 usages
          500: '#6b7280', // measured — muted / secondary text
          400: '#99a1af', // interpolated — was undefined, 17 usages
          300: '#d1d5dc', // measured — borders, disabled edges, placeholder icons

          /**
           * Buyer primary text. Figma confirms the buyer surface genuinely uses
           * #1a1a1a, not the #101828 used by seller and realtor (node 228:20943).
           *
           * SCRUM-164 standardised all three onto #101828 for consistency, which
           * moved buyer off its designed value. Product owner chose fidelity over
           * consistency (SCRUM-173), so buyer is back on #1a1a1a.
           *
           * DO NOT "harmonise" this into ink-900. The three surfaces genuinely
           * diverge on several axes — card radius is 20/16/14, badge tints are
           * none/-50/-100, and this is the text colour. All measured, all
           * intentional as far as we can tell.
           */
          buyer: '#1a1a1a',
        },

        surface: {
          page: '#f9fafb', // seller + realtor page background
          card: '#ffffff',
          warm: '#f5f1e8', // insight / tip rails — seller 3.21%, realtor 1.47%
          muted: '#f3f4f6', // inactive pill and chip fill
          tint: '#ebefee', // muted green icon chips

          /**
           * Landing-page alternating bands (SCRUM-178). Measured by column
           * scanline down the 1577×7215 export: `paper` at y1248-2407 (featured),
           * y5357-6070 (financing); `linen` at y4459-5113 (testimonials).
           *
           * These are WARM neutrals and `surface-page` is COOL (#f9fafb is
           * blue-tinted). Reusing `surface-page` here reads visibly grey-blue
           * against `emerald-deep`. Adding rather than remapping because
           * `surface-page` is the measured value for the seller and realtor
           * app surfaces and must not move.
           */
          paper: '#f7f7f5',
          linen: '#f9f7f3',

          /**
           * Gold-tinted icon chip on the onboarding financing slide (SCRUM-184,
           * measured 2.29% of `onboarding-3.png`). The other two slides use
           * `surface-tint`; this one is warmer to pair with the gold glyph.
           *
           * Distinct from `bone` (#f6f4ee) and `surface-warm` (#f5f1e8) — both
           * are measurably darker, and swapping either in reads as a dirty
           * cream against the gold rather than a tint of it.
           */
          gold: '#faf8f0',
        },

        line: {
          DEFAULT: '#e5e7eb', // header rule, sidebar rule, dividers
          strong: '#d1d5dc', // input borders
        },

        /**
         * Reserved for affirmative and destructive *actions* — Accept Offer,
         * Reject Offer, "Yes, Verified". Not for completion or progress
         * indicators: those are `emerald-deep`, confirmed by measurement.
         */
        status: {
          success: '#00a63e',
          danger: '#e7000b',
          urgent: '#fb2c36', // discount / urgency badge
          gold: '#c9a646', // deal-time icon, premium marker
        },

        /**
         * Inspection / report state chrome, measured from Figma node 280:5555
         * (realtor Assigned Inspections, SCRUM-204).
         *
         * ⚠️ These are NOT stock Tailwind. The design is drawn against Tailwind
         * v4's palette and this app is on v3.4, so `bg-amber-100 text-amber-700`
         * renders v3.4's values — visibly off-design on the -700 text in
         * particular (#b45309 vs #bb4d00, #15803d vs #008236, #1d4ed8 vs
         * #1447e6). Same class of bug as SCRUM-166's red-500 (#ef4444 vs
         * #fb2c36), which became `status-urgent` for exactly this reason.
         *
         * The -50/-100 split is deliberate and measured, not drift: the summary
         * TILES use the -50 fill and the row STATUS PILLS use -100, and both
         * share the same -200 border. That is consistent with the "realtor
         * badges are -100" finding in SCRUM-171/172 — the tiles are simply new
         * UI drawn one step lighter.
         */
        pending: {
          50: '#fffbeb', // tile fill
          100: '#fef3c6', // pill fill
          200: '#fee685', // border, both
          700: '#bb4d00', // text, both
        },
        scheduled: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bedbff',
          700: '#1447e6',
        },
        done: {
          50: '#f0fdf4',
          100: '#dcfce7',
          200: '#b9f8cf',
          700: '#008236',
          // Heading ink inside the wizard's Progress card (Figma 278:3927).
          800: '#0d542b',
        },
        /** Distress-sale marker, and the negative selected state on the report
         * wizard's option cards. `50` is the wizard's fill; `100` is the row
         * badge's (Figma 278:3764). */
        distress: {
          50: '#fef2f2',
          100: '#ffe2e2',
          700: '#c10007',
        },
      },

      /**
       * The design sits on a 4px grid, which Tailwind's default scale already
       * follows — 44px padding is `p-11`, 36px gap is `gap-9`, 48px controls
       * are `h-12`. Only these two steps are missing from the default scale.
       */
      spacing: {
        15: '3.75rem', // 60px — stat-card icon chip (measured y213-272)
        18: '4.5rem', // 72px — header height, search input height
      },

      /**
       * ⚠️ Card radius differs per surface in the design — buyer 20px, seller
       * 16px (`rounded-2xl`), realtor 14px. Border treatment differs too: buyer
       * is #e5e7eb at 50% opacity, seller and realtor are solid.
       *
       * These are measured, not assumed, but 20/16/14 is close enough that it
       * may be unintentional drift in the design rather than three deliberate
       * choices. Flagged for the designer (SCRUM-172). Encoded faithfully until
       * someone confirms otherwise — guessing at "they meant one value" would
       * be inventing.
       */
      borderRadius: {
        /**
         * Buyer, 20px. Corrected in SCRUM-169 from a pixel-measured 16px — the
         * corner probe found where pure #ffffff begins, which undercounts the
         * arc. Figma node 228:20937 gives `rounded-[21.194px]`; at that frame's
         * 1.0597 scale factor, exactly 20px.
         */
        card: '1.25rem',
        /** Realtor, 14px — Figma node 276:87. Seller uses stock `rounded-2xl`. */
        'card-sm': '0.875rem',
      },

      /**
       * NOTE: there is deliberately no `shadow-card`.
       *
       * SCRUM-163 concluded from pixel measurement that cards use a shadow and
       * no border. That was WRONG. Figma (228:20937) gives:
       *   border-[1.06px] border-[rgba(229,231,235,0.5)] border-solid
       * — a 1px #e5e7eb border at 50% opacity, and no shadow at all.
       *
       * A half-opacity border composited over white produces a soft two-pixel
       * ramp (#f5f5f6 -> #f8f8f9) that is indistinguishable from a small shadow
       * in a raster. Border-vs-shadow cannot be resolved from a PNG — take it
       * from Figma. Cards use `border border-line/50`.
       */

      /**
       * Confirmed against Figma in SCRUM-169. Values are the frame's numbers
       * divided by its 1.0597 scale factor. The PNG-inferred sizes were close
       * (~18 / ~40 vs actual 17.5 / 37.5), so the inference held up.
       *
       * The design specifies Inter throughout. The app keeps Archivo + Fraunces
       * — a deliberate brand choice, and Inter may simply be the designer's
       * default. Sizes are corrected here; the typeface is not, pending
       * confirmation with the designer.
       */
      fontSize: {
        stat: ['2.375rem', { lineHeight: '2.8125rem' }], // 38/45 — 228:20943
        'heading-lg': ['2.375rem', { lineHeight: '2.8125rem' }],
        field: ['1.25rem', { lineHeight: '1.4' }], // 20px — search placeholder, 228:20974
        'label-lg': ['1.125rem', { lineHeight: '1.5625rem' }], // 18/25 — 228:20941
      },
    },
  },
  plugins: [],
};

export default config;
