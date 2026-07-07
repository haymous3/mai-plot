/** Deal-progress mapping for the buyer Deal Progress tracker + Active Deals card
 * (SCRUM-95). Maps the transaction state-machine stage onto the 6 design
 * milestones. */

export const DEAL_MILESTONES = [
  { title: 'Bid Submitted', desc: 'You placed a bid on this property.' },
  { title: 'Seller Accepted', desc: 'The seller reviewed and accepted your bid.' },
  { title: 'Document Verification', desc: 'Our legal team is verifying the property documents.' },
  { title: 'Financing & Escrow', desc: 'Funds deposited in escrow pending transfer.' },
  { title: 'Title Transfer', desc: 'Ownership documents transferred to your name.' },
  { title: 'Keys Handover', desc: 'Take possession of your new property.' },
] as const;

export const DEAL_TOTAL_STEPS = DEAL_MILESTONES.length;

// How many of the 6 milestones are complete at each state-machine stage.
const STAGE_COMPLETED: Record<string, number> = {
  offer_accepted: 2,
  inspection_scheduled: 2,
  inspection_completed: 3,
  loan_applied: 3,
  loan_approved: 4,
  loan_rejected: 3,
  payment_held: 4,
  title_held: 5,
  completed: 6,
  cancelled: 1,
  disputed: 2,
  resolved: 3,
};

const STAGE_LABELS: Record<string, string> = {
  offer_accepted: 'Offer accepted',
  inspection_scheduled: 'Inspection scheduled',
  inspection_completed: 'Document verification',
  loan_applied: 'Loan applied',
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

export function dealCompletedSteps(stage: string): number {
  return STAGE_COMPLETED[stage] ?? 1;
}

export function dealStageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage.replace(/_/g, ' ');
}

export function isDealActive(stage: string): boolean {
  return !TERMINAL.has(stage);
}
