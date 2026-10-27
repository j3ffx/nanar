import { describe, expect, it } from 'vitest';

import { keyFromHash } from './usePairing';

describe('keyFromHash', () => {
  it('reads the key the QR code carries', () => {
    expect(keyFromHash('#k=AbC-123_x')).toBe('AbC-123_x');
  });

  it('finds nothing in an ordinary address', () => {
    expect(keyFromHash('')).toBeNull();
    expect(keyFromHash('#top')).toBeNull();
  });
});
