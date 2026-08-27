/**
 * Nigerian bank codes for the Settings payout-account form (SCRUM-188).
 *
 * ⚠️ WHY THIS LIST EXISTS. `PUT /payout-account` takes a `bank_code`
 * (`^\d{3,10}$`), but the design draws a free-text "Bank Name" field. There is
 * no bank-list endpoint anywhere in the platform, so the name→code mapping has
 * to come from somewhere. A hardcoded list of the banks the product already
 * names elsewhere is honest and works offline.
 *
 * ⚠️ THIS IS A STOPGAP. Paystack exposes `GET /bank`, which is the durable
 * answer: it stays current as banks merge, rebrand or are licensed, and it is
 * the same source Paystack validates the transfer recipient against. Codes
 * below are the standard CBN/NIBSS institution codes Paystack uses; if one
 * drifts, `set_account` fails at recipient creation with RECIPIENT_UNAVAILABLE
 * rather than silently misrouting money — the failure is loud, which is the
 * right side to err on.
 *
 * Ordered as the landing page's trust bar lists them, then alphabetically.
 */

export type Bank = { code: string; name: string };

export const NIGERIAN_BANKS: readonly Bank[] = [
  { code: '044', name: 'Access Bank' },
  { code: '058', name: 'GTBank' },
  { code: '057', name: 'Zenith Bank' },
  { code: '011', name: 'First Bank of Nigeria' },
  { code: '033', name: 'United Bank for Africa (UBA)' },
  { code: '221', name: 'Stanbic IBTC Bank' },
  { code: '214', name: 'First City Monument Bank (FCMB)' },
  { code: '070', name: 'Fidelity Bank' },
  { code: '050', name: 'Ecobank Nigeria' },
  { code: '084', name: 'Enterprise Bank' },
  { code: '030', name: 'Heritage Bank' },
  { code: '082', name: 'Keystone Bank' },
  { code: '076', name: 'Polaris Bank' },
  { code: '101', name: 'Providus Bank' },
  { code: '068', name: 'Standard Chartered Bank' },
  { code: '232', name: 'Sterling Bank' },
  { code: '100', name: 'Suntrust Bank' },
  { code: '032', name: 'Union Bank of Nigeria' },
  { code: '035', name: 'Wema Bank' },
  { code: '999992', name: 'OPay' },
  { code: '999991', name: 'PalmPay' },
  { code: '50211', name: 'Kuda Bank' },
  { code: '090267', name: 'Kuda Microfinance Bank' },
  { code: '565', name: 'Carbon' },
] as const;

/** Display name for a stored code, falling back to the code itself. */
export function bankName(code: string): string {
  return NIGERIAN_BANKS.find((b) => b.code === code)?.name ?? code;
}
