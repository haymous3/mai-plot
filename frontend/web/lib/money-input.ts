/**
 * Thousands-grouping for money INPUTS (SCRUM-202).
 *
 * `formatNaira` in lib/format.ts renders a stored kobo amount for DISPLAY.
 * This is the other direction: what a user sees while they type, so
 * `10000000` reads as `10,000,000` instead of a wall of zeros nobody can
 * count.
 *
 * The shape everywhere is: STATE HOLDS DIGITS, the input DISPLAYS the grouped
 * form. Keeping state raw means every existing `Number(...) * 100` conversion
 * to kobo keeps working untouched — commas never reach the arithmetic, so
 * there is no chance of `Number("10,000,000")` quietly becoming NaN and
 * writing a wrong amount (CLAUDE.md §4: money is BIGINT kobo, never a float).
 *
 * Lives here rather than in a component because `vitest.config.ts` collects
 * `lib/**` only, and the caret maths below is the kind of thing that is
 * obviously right and quietly wrong.
 */

/** Everything that is not a digit, removed. Also drops a leading-zero run so
 * "007" reads as "7" — a leading zero in an amount is never meant. */
export function digitsOnly(value: string): string {
  const digits = value.replace(/\D/g, '');
  const trimmed = digits.replace(/^0+(?=\d)/, '');
  return trimmed;
}

/** Group digits in threes: "10000000" -> "10,000,000". */
export function groupDigits(value: string): string {
  const digits = digitsOnly(value);
  if (!digits) return '';
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Where the caret belongs after grouping is applied.
 *
 * Without this the caret jumps to the end of the field the moment a comma is
 * inserted, because the formatted string is longer than what the user typed
 * and React restores the caret by raw index. Correcting a digit in the middle
 * of an amount then becomes impossible.
 *
 * The stable thing across formatting is HOW MANY DIGITS sit before the caret,
 * not how many characters. So: count digits up to the caret in the raw input,
 * then walk the formatted string until that many digits have been passed.
 */
export function caretAfterGrouping(rawValue: string, rawCaret: number, formatted: string): number {
  const digitsBefore = (rawValue.slice(0, rawCaret).match(/\d/g) ?? []).length;
  if (digitsBefore === 0) {
    // Caret sat before any digit — keep it at the start rather than letting it
    // land after a leading comma, which cannot happen but reads badly if it did.
    return 0;
  }
  let seen = 0;
  for (let i = 0; i < formatted.length; i += 1) {
    if (/\d/.test(formatted[i])) {
      seen += 1;
      if (seen === digitsBefore) return i + 1;
    }
  }
  return formatted.length;
}

/**
 * Naira digits to kobo, as a safe integer.
 *
 * Accepts either the raw or the grouped form so a caller cannot get it wrong,
 * and returns 0 for empty input rather than NaN. Multiplication is on an
 * integer, never a parsed float — 1 naira is exactly 100 kobo.
 */
export function nairaToKobo(value: string): number {
  const digits = digitsOnly(value);
  if (!digits) return 0;
  return Number(digits) * 100;
}
