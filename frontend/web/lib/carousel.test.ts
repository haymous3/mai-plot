import { describe, expect, it } from 'vitest';

import { pageCount, pageItems, stepPage } from './carousel';

describe('pageCount', () => {
  it('divides evenly', () => {
    expect(pageCount(4, 2)).toBe(2);
  });

  it('rounds up a partial last page', () => {
    expect(pageCount(5, 2)).toBe(3);
  });

  it('is 0 for an empty list, so the controls can be hidden entirely', () => {
    expect(pageCount(0, 2)).toBe(0);
  });

  it('is 0 rather than Infinity when perPage is nonsense', () => {
    expect(pageCount(4, 0)).toBe(0);
    expect(pageCount(4, -1)).toBe(0);
  });
});

describe('stepPage', () => {
  it('advances', () => {
    expect(stepPage(0, 1, 3)).toBe(1);
  });

  it('wraps forward off the end', () => {
    expect(stepPage(2, 1, 3)).toBe(0);
  });

  // The design draws prev/next always enabled — there is no disabled state
  // anywhere in the export — so going back from page 0 must land somewhere
  // real rather than clamping to a no-op.
  it('wraps backward off the start', () => {
    expect(stepPage(0, -1, 3)).toBe(2);
  });

  it('handles a delta larger than the page count', () => {
    expect(stepPage(0, 7, 3)).toBe(1);
    expect(stepPage(0, -7, 3)).toBe(2);
  });

  it('stays at 0 when there are no pages', () => {
    expect(stepPage(0, 1, 0)).toBe(0);
  });
});

describe('pageItems', () => {
  const items = ['a', 'b', 'c', 'd', 'e'];

  it('returns the slice for a page', () => {
    expect(pageItems(items, 0, 2)).toEqual(['a', 'b']);
    expect(pageItems(items, 1, 2)).toEqual(['c', 'd']);
  });

  it('returns a short slice for a partial last page', () => {
    expect(pageItems(items, 2, 2)).toEqual(['e']);
  });

  it('returns nothing past the end rather than throwing', () => {
    expect(pageItems(items, 9, 2)).toEqual([]);
  });

  it('returns nothing for invalid input', () => {
    expect(pageItems(items, -1, 2)).toEqual([]);
    expect(pageItems(items, 0, 0)).toEqual([]);
  });
});
