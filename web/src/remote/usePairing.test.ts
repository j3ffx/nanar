import { describe, expect, it } from 'vitest';

import { fallbackUrl, keyFromHash } from './usePairing';

describe('fallbackUrl', () => {
  it('carries the key: the other address has no cookie of its own', () => {
    expect(fallbackUrl('192.168.1.10:8642', '/bibliotheque', 'abc')).toBe(
      'http://192.168.1.10:8642/bibliotheque#k=abc',
    );
    expect(keyFromHash(new URL(fallbackUrl('nanar.local:8642', '/', 'abc')).hash)).toBe('abc');
  });

  it('still moves without a key', () => {
    expect(fallbackUrl('192.168.1.10:8642', '/', null)).toBe('http://192.168.1.10:8642/');
  });
});

describe('keyFromHash', () => {
  it('reads the key the QR code carries', () => {
    expect(keyFromHash('#k=AbC-123_x')).toBe('AbC-123_x');
  });

  it('finds nothing in an ordinary address', () => {
    expect(keyFromHash('')).toBeNull();
    expect(keyFromHash('#top')).toBeNull();
  });
});
