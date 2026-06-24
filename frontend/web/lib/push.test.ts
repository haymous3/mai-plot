import { describe, expect, it } from 'vitest';

import { clickTargetPath, urlBase64ToUint8Array } from './push';

describe('urlBase64ToUint8Array', () => {
  it('decodes a padded base64url string to its bytes', () => {
    // "SGVsbG8" (base64url, no padding) == base64 "SGVsbG8=" == "Hello".
    expect(Array.from(urlBase64ToUint8Array('SGVsbG8'))).toEqual([72, 101, 108, 108, 111]);
  });

  it('handles base64url - and _ substitutions', () => {
    // bytes [251, 255] => base64 "+/8=" => base64url "-_8" (exercises - and _).
    expect(Array.from(urlBase64ToUint8Array('-_8'))).toEqual([251, 255]);
  });

  it('produces a key of the expected length for a VAPID-sized key', () => {
    // A real applicationServerKey decodes to 65 bytes (uncompressed P-256 point):
    // 87 base64url chars (no padding) -> 65 bytes.
    const key = 'BEl' + 'A'.repeat(84); // 87 chars
    expect(urlBase64ToUint8Array(key)).toHaveLength(65);
  });
});

describe('clickTargetPath', () => {
  it('returns a same-origin relative path', () => {
    expect(clickTargetPath({ type: 'offer_accepted', reference_id: 'abc' }).startsWith('/')).toBe(
      true,
    );
  });

  it('never throws on null / missing payload', () => {
    expect(clickTargetPath(null)).toBe('/');
    expect(clickTargetPath(undefined)).toBe('/');
    expect(clickTargetPath({})).toBe('/');
  });
});
