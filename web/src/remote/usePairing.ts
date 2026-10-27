import { useCallback, useEffect, useState } from 'react';

import { ApiError, isPaired, pair } from '@/lib/api';

export type PairingStatus = 'checking' | 'paired' | 'unpaired' | 'wrong-key' | 'offline';

/** Reads the key a QR code put after the `#k=`, out of the address bar. */
export function keyFromHash(hash: string): string | null {
  return new URLSearchParams(hash.replace(/^#/, '')).get('k');
}

/**
 * Pairs with the key from the QR code when the page was opened from it, then tells whether this
 * phone may drive Nanar. `recheck` runs again (after Nanar said "pairing required").
 */
export function usePairing(): { status: PairingStatus; recheck: () => void } {
  const [status, setStatus] = useState<PairingStatus>('checking');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const run = async () => {
      const key = keyFromHash(location.hash);
      if (key) {
        // Out of the address bar (and of the history) as soon as it has been read.
        history.replaceState(null, '', location.pathname + location.search);
        try {
          await pair(key);
        } catch (error) {
          if (error instanceof ApiError && error.code === 'wrong_key') {
            if (alive) setStatus('wrong-key');
            return;
          }
        }
      }
      try {
        const paired = await isPaired();
        if (alive) setStatus(paired ? 'paired' : 'unpaired');
      } catch {
        if (!alive) return;
        setStatus('offline');
        retry = setTimeout(() => setAttempt((n) => n + 1), 3000);
      }
    };
    void run();
    return () => {
      alive = false;
      clearTimeout(retry);
    };
  }, [attempt]);

  // A QR code scanned while the page is already open only changes the hash.
  useEffect(() => {
    const onHash = () => {
      if (keyFromHash(location.hash)) setAttempt((n) => n + 1);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const recheck = useCallback(() => setAttempt((n) => n + 1), []);
  return { status, recheck };
}
