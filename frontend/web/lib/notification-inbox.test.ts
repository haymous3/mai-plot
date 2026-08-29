import { describe, expect, it } from 'vitest';

import { INBOX_TABS, accentFor, headingFor, isInboxTab, parseTab } from './notification-inbox';

describe('parseTab', () => {
  it('accepts every real tab', () => {
    for (const t of INBOX_TABS) expect(parseTab(t)).toBe(t);
  });

  it('falls back to All for anything unrecognised', () => {
    // The value comes off the query string, so it is untrusted input.
    expect(parseTab(undefined)).toBe('all');
    expect(parseTab('')).toBe('all');
    expect(parseTab('nonsense')).toBe('all');
  });

  it('does not accept messages', () => {
    // No messaging feature exists; the design's tab was dropped rather than
    // shipped as a control that could never fill.
    expect(isInboxTab('messages')).toBe(false);
    expect(parseTab('messages')).toBe('all');
  });
});

describe('accentFor', () => {
  it('paints offers, documents and money distinctly', () => {
    expect(accentFor('offer_received')).toBe('offer');
    expect(accentFor('offer_accepted')).toBe('offer');
    expect(accentFor('document_verified')).toBe('document');
    expect(accentFor('poa_rejected')).toBe('document');
    expect(accentFor('loan_disbursed')).toBe('money');
    expect(accentFor('title_released')).toBe('money');
    expect(accentFor('deposit_confirmed')).toBe('money');
  });

  it('falls back to system for an unknown type, matching the server catch-all', () => {
    // A row must never render unstyled just because a new producer shipped.
    expect(accentFor('a_type_shipped_after_this_ticket')).toBe('system');
    expect(accentFor('listing_approved')).toBe('system');
  });

  it('does not paint a document row as money', () => {
    // The visual family has to agree with the tab the server filed it under.
    expect(accentFor('document_rejected')).not.toBe('money');
  });
});

describe('headingFor', () => {
  it('prefers the notification title', () => {
    expect(headingFor({ title: 'New offer', type: 'offer_received' })).toBe('New offer');
  });

  it('humanises the type when there is no title', () => {
    // notifications.title is nullable, so a blank row is reachable.
    expect(headingFor({ title: null, type: 'offer_received' })).toBe('Offer received');
    expect(headingFor({ title: '   ', type: 'document_verified' })).toBe('Document verified');
  });

  it('never returns an empty heading', () => {
    expect(headingFor({ title: '', type: 'x' })).not.toBe('');
  });
});
