import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{js,ts,jsx,tsx,mdx}', './components/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['var(--font-display)', 'ui-serif', 'Georgia', 'serif'],
      },
      colors: {
        // Deep institutional ink + a distressed-asset emerald accent.
        ink: {
          900: '#0d1714',
          800: '#16231f',
          700: '#22332d',
          500: '#46564f',
          300: '#9aa8a1',
        },
        emerald: {
          accent: '#1f7a5a',
          deep: '#0f3d2e',
        },
        bone: '#f6f4ee',
      },
    },
  },
  plugins: [],
};

export default config;
