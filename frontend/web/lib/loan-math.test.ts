import { describe, expect, it } from 'vitest';

import { bpsToPercent, monthlyPaymentKobo, totalInterestKobo, totalRepaymentKobo } from './loan-math';

// ₦22.5M principal, 12% p.a., 12 months — the Figma worked example.
const P = 2_250_000_000;

describe('loan maths (simple annual interest)', () => {
  it('matches the Figma worked example', () => {
    expect(totalInterestKobo(P, 1200, 12)).toBe(270_000_000); // ₦2.7M
    expect(totalRepaymentKobo(P, 1200, 12)).toBe(2_520_000_000); // ₦25.2M
    expect(monthlyPaymentKobo(P, 1200, 12)).toBe(210_000_000); // ₦2.1M
  });

  it('scales interest with tenure', () => {
    expect(totalInterestKobo(P, 1200, 6)).toBe(135_000_000); // half a year → half the interest
  });

  it('returns zero for non-positive inputs', () => {
    expect(totalInterestKobo(0, 1200, 12)).toBe(0);
    expect(monthlyPaymentKobo(P, 1200, 0)).toBe(0);
    expect(totalInterestKobo(P, 0, 12)).toBe(0);
  });
});

describe('bpsToPercent', () => {
  it('formats whole and fractional rates', () => {
    expect(bpsToPercent(1200)).toBe('12%');
    expect(bpsToPercent(1150)).toBe('11.5%');
  });
});
