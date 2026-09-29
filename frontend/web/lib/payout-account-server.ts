import { transactionServiceUrl } from '@/lib/api';
import type { PayoutAccount } from '@/lib/payout-account';
import { sessionBackendGet } from '@/lib/session-api';

/**
 * The caller's payout account, read server-side (SCRUM-223).
 *
 * THREE outcomes, on purpose: `missing` is a confirmed 404 and is what the
 * dashboard nudge keys on; `unknown` (service down, anything else) renders no
 * nudge at all. Telling someone "add your payout account" because a read failed
 * would send them to re-enter details they already gave.
 */
export type PayoutAccountStatus =
  | { status: 'set'; account: PayoutAccount }
  | { status: 'missing' }
  | { status: 'unknown' };

export async function readPayoutAccount(): Promise<PayoutAccountStatus> {
  const result = await sessionBackendGet<PayoutAccount>(`${transactionServiceUrl()}/payout-account`);
  if (result.ok) return { status: 'set', account: result.data };
  if (result.status === 404) return { status: 'missing' };
  return { status: 'unknown' };
}
