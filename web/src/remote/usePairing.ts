import { useCallback, useEffect, useState } from 'react';

import { ApiError, isPaired, pair } from '@/lib/api';

export type PairingStatus = 'checking' | 'paired' | 'unpaired' | 'wrong-key' | 'offline';

/** The name Nanar announces on the local network (src/nanar/discovery.py). */
export const NAME = 'nanar.local';

/** Whether Nanar answers under that name from this phone, within a second and a half. */
async function answers(name: string): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1500);
  try {
    const response = await fetch(`http://${name}:${location.port || '80'}/api/health`, {
      signal: controller.signal,
      cache: 'no-store',
    });
    return response.ok;
  } catch {
    return false; // the phone can't resolve .local names, or the network keeps it from them
  } finally {
    clearTimeout(timer);
  }
}

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
        // Opened by the PC's IP address (the QR code): move to nanar.local if this phone
        // reaches it, so that the pairing and the home screen icon outlive a change of Wi-Fi.
        if (location.hostname !== NAME && (await answers(NAME))) {
          location.replace(`http://${NAME}:${location.port || '80'}/#k=${key}`);
          return;
        }
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
