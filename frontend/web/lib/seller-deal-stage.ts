/** Seller-framed transaction progress (SCRUM-98). Maps the state-machine stage
 * onto the 7 milestones in the seller Transactions design. Separate from the
 * buyer's lib/deal-stage.ts, which is buyer-framed. */

export const SELLER_MILESTONES = [
  { title: 'Offer Accepted', desc: 'You accepted the buyer’s offer.' },
  { title: 'Deposit Made', desc: 'The buyer paid their deposit.' },
  { title: 'Inspection Scheduled', desc: 'A property inspection is arranged.' },
  { title: 'Loan Processing', desc: 'Awaiting loan approval from the buyer’s lender.' },
  { title: 'Payment in Escrow', desc: 'Funds are held in escrow.' },
  { title: 'Title Transfer in Progress', desc: 'Ownership documents are being transferred.' },
  { title: 'Completed', desc: 'The sale is complete.' },
] as const;

export const SELLER_TOTAL_STEPS = SELLER_MILESTONES.length;

// How many of the 7 milestones are complete at each state-machine stage.
const STAGE_COMPLETED: Record<string, number> = {
  offer_accepted: 1,
  inspection_scheduled: 3,
  inspection_completed: 3,
  loan_applied: 4,
  loan_approved: 4,
  loan_rejected: 4,
  payment_held: 5,
  title_held: 6,
  completed: 7,
  cancelled: 1,
  disputed: 3,
  resolved: 4,
};

const STAGE_LABELS: Record<string, string> = {
  offer_accepted: 'Offer accepted',
  inspection_scheduled: 'Inspection scheduled',
  inspection_completed: 'Inspection completed',
  loan_applied: 'Loan processing',
  loan_approved: 'Loan approved',
  loan_rejected: 'Loan rejected',
  payment_held: 'Payment in escrow',
  title_held: 'Title transfer',
  completed: 'Completed',
  cancelled: 'Cancelled',
  disputed: 'Disputed',
  resolved: 'Resolved',
};

const TERMINAL = new Set(['completed', 'cancelled', 'loan_rejected']);

export function sellerCompletedSteps(stage: string): number {
  return STAGE_COMPLETED[stage] ?? 1;
}

export function sellerStageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage.replace(/_/g, ' ');
}

export function isSaleActive(stage: string): boolean {
  return !TERMINAL.has(stage);
}
