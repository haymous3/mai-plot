/**
 * Loan repayment maths for the buyer calculator (SCRUM-94).
 *
 * Simple annual interest, matching the Figma calculator: for ₦22.5M over 12
 * months at 12% p.a. → ₦2.7M interest, ₦25.2M total, ₦2.1M/month. All amounts
 * are BIGINT kobo (CLAUDE.md) and results are whole kobo. Pure + dependency-free
 * so the estimate is unit-tested and identical on server and client.
 *
 * This is a display estimate only — the binding terms come from the bank's
 * decision (loans.monthly_instalment_kobo), which the status page prefers when
 * present.
 */

const BPS_DIVISOR = 10_000;
const MONTHS_PER_YEAR = 12;

/** Total simple interest over the tenure, in kobo. */
export function totalInterestKobo(
  principalKobo: number,
  annualRateBps: number,
  tenureMonths: number,
): number {
  if (principalKobo <= 0 || annualRateBps <= 0 || tenureMonths <= 0) return 0;
  return Math.round(
    (principalKobo * annualRateBps * tenureMonths) / (BPS_DIVISOR * MONTHS_PER_YEAR),
  );
}

/** Principal + total interest, in kobo. */
export function totalRepaymentKobo(
  principalKobo: number,
  annualRateBps: number,
  tenureMonths: number,
): number {
  return principalKobo + totalInterestKobo(principalKobo, annualRateBps, tenureMonths);
}

/** Equal monthly instalment, in kobo. */
export function monthlyPaymentKobo(
  principalKobo: number,
  annualRateBps: number,
  tenureMonths: number,
): number {
  if (tenureMonths <= 0) return 0;
  return Math.round(totalRepaymentKobo(principalKobo, annualRateBps, tenureMonths) / tenureMonths);
}

/** Basis points as a percent string, e.g. 1200 -> "12%". */
export function bpsToPercent(bps: number): string {
  const pct = bps / 100;
  return `${Number.isInteger(pct) ? pct : pct.toFixed(1)}%`;
}
