/**
 * 48-hour PoA review SLA (SCRUM-61). The legal team should action a submission
 * within 48h of upload; this computes the remaining time (or overdue amount)
 * for the per-row countdown. Pure + dependency-free for unit testing.
 */

const SLA_HOURS = 48;
const MS_PER_HOUR = 60 * 60 * 1000;

export interface SlaStatus {
  overdue: boolean;
  /** Hours remaining (or overdue, when negative). */
  hoursRemaining: number;
  /** Short human label, e.g. "12h 30m left" or "5h 10m overdue". */
  label: string;
}

export function slaStatus(submittedAtIso: string, now: Date): SlaStatus {
  const submitted = new Date(submittedAtIso).getTime();
  if (Number.isNaN(submitted)) {
    return { overdue: false, hoursRemaining: SLA_HOURS, label: '—' };
  }
  const deadline = submitted + SLA_HOURS * MS_PER_HOUR;
  const remainingMs = deadline - now.getTime();
  const overdue = remainingMs <= 0;

  const absMs = Math.abs(remainingMs);
  const hours = Math.floor(absMs / MS_PER_HOUR);
  const minutes = Math.floor((absMs % MS_PER_HOUR) / (60 * 1000));
  const span = `${hours}h ${minutes}m`;

  return {
    overdue,
    hoursRemaining: remainingMs / MS_PER_HOUR,
    label: overdue ? `${span} overdue` : `${span} left`,
  };
}
