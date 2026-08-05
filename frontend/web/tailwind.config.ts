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
  content: ['./app/**/*.{js,ts,jsx,tsx,mdx}', './components/**/*.{js,ts,jsx,tsx,mdx}'],
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
          900: '#101828', // measured — primary text
          800: '#1e2939', // interpolated
          700: '#364153', // interpolated
          600: '#4a5565', // interpolated — was undefined, 41 usages
          500: '#6b7280', // measured — muted / secondary text
          400: '#99a1af', // interpolated — was undefined, 17 usages
          300: '#d1d5dc', // measured — borders, disabled edges, placeholder icons
        },

        surface: {
          page: '#f9fafb', // seller + realtor page background
          card: '#ffffff',
          warm: '#f5f1e8', // insight / tip rails — seller 3.21%, realtor 1.47%
          muted: '#f3f4f6', // inactive pill and chip fill
          tint: '#ebefee', // muted green icon chips
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
