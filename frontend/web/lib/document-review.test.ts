import { describe, expect, it } from 'vitest';

import type { DocQueueItem } from './api';
import { describeDocument, describeOwner, formatFileSize } from './document-review';

function item(overrides: Partial<DocQueueItem>): DocQueueItem {
  return {
    id: 'doc-1',
    source: 'listing',
    verification_status: 'pending',
    created_at: '2026-08-28T09:00:00Z',
    listing_id: null,
    document_type: null,
    user_id: null,
    owner_name: null,
    category: null,
    file_name: null,
    size_bytes: null,
    ...overrides,
  };
}

describe('describeDocument', () => {
  it('names a known property document type', () => {
    expect(describeDocument(item({ document_type: 'c_of_o' }))).toBe('Certificate of Occupancy');
  });

  it('humanises an unknown type rather than showing a raw slug', () => {
    expect(describeDocument(item({ document_type: 'land_receipt' }))).toBe('land receipt');
  });

  it('uses the uploaded filename for a personal document', () => {
    expect(
      describeDocument(item({ source: 'personal', file_name: 'nin-slip.pdf' })),
    ).toBe('nin-slip.pdf');
  });

  it('never returns an empty label', () => {
    expect(describeDocument(item({}))).toBe('Document');
    expect(describeDocument(item({ source: 'personal' }))).toBe('Untitled document');
  });
});

describe('formatFileSize', () => {
  it('returns null when the table records no size', () => {
    // listing_documents has no size_bytes column at all.
    expect(formatFileSize(null)).toBeNull();
  });

  it('scales through bytes, kilobytes and megabytes', () => {
    expect(formatFileSize(512)).toBe('512 B');
    expect(formatFileSize(248000)).toBe('242 KB');
    expect(formatFileSize(1887436)).toBe('1.8 MB');
  });

  it('handles the unit boundaries', () => {
    expect(formatFileSize(1023)).toBe('1023 B');
    expect(formatFileSize(1024)).toBe('1 KB');
    expect(formatFileSize(1024 * 1024)).toBe('1.0 MB');
  });

  it('does not render a nonsensical negative size', () => {
    expect(formatFileSize(-1)).toBeNull();
  });
});

describe('describeOwner', () => {
  it('prefers the owner name', () => {
    expect(
      describeOwner(item({ source: 'personal', owner_name: 'Ada Obi', user_id: 'u-1' })),
    ).toBe('Ada Obi');
  });

  it('falls back to the id when the owner has no user_pii row', () => {
    // The queue LEFT JOINs user_pii precisely so this row still appears; it
    // has to stay actionable rather than collapsing to a dash.
    expect(describeOwner(item({ source: 'personal', user_id: 'u-1' }))).toBe('u-1');
  });

  it('shows the listing for a property document', () => {
    expect(describeOwner(item({ listing_id: 'l-9' }))).toBe('l-9');
  });

  it('degrades to a dash when there is nothing to show', () => {
    expect(describeOwner(item({ source: 'personal' }))).toBe('—');
    expect(describeOwner(item({}))).toBe('—');
  });
});
