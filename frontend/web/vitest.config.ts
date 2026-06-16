import { defineConfig } from 'vitest/config';

// Unit tests cover the pure helpers (IP allowlist, role checks) that gate admin
// access — no DOM/component rendering needed, so the default node environment
// is enough.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['lib/**/*.test.ts'],
  },
});
