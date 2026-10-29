import { useCallback, useEffect, useState } from 'react';

import { ApiError, fetchPairing, isPaired, pair } from '@/lib/api';

export type PairingStatus = 'checking' | 'paired' | 'unpaired' | 'wrong-key' | 'offline';

/**
 * Moving to nanar.local: `trying` while the phone looks for it, `unreachable` once it gave up
 * (with why: `timeout` when the name never answered, `refused` when the browser stopped the
 * request at once), `null` when there is nothing to do (already there, or no name announced).
 * A browser may refuse a page's request to a .local name yet open it when asked to: `url` is a
 * link to nanar.local carrying the key, for the phone's owner to try.
 */
export type Hop =
  { state: 'trying' } | { state: 'unreachable'; why: 'timeout' | 'refused'; url: string } | null;

/** The name Nanar announces on the local network (src/nanar/discovery.py). */
export const NAME = 'nanar.local';

const TRIES = 3;
const TRY_MS = 5000; // a phone's first lookup of a .local name can take seconds

/** Asks `host` (name:port) for Nanar's health: 'ok', or why it did not answer. */
async function probe(host: string): Promise<'ok' | 'timeout' | 'refused'> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TRY_MS);
  const started = performance.now();
  try {
    const response = await fetch(`http://${host}/api/health`, {
      signal: controller.signal,
      cache: 'no-store',
    });
    return response.ok ? 'ok' : 'refused';
  } catch {
    // Failing at once means the browser refused; failing late, that nothing answered.
    return controller.signal.aborted || performance.now() - started > 1000 ? 'timeout' : 'refused';
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
 *
 * The QR code holds the PC's IP address, which always works but changes with the Wi-Fi. Once
 * paired there, the page looks for nanar.local in the background and moves there when it
 * answers, so that the pairing and the home screen icon outlive a change of network.
 */
export function usePairing(): { status: PairingStatus; hop: Hop; recheck: () => void } {
  const [status, setStatus] = useState<PairingStatus>('checking');
  const [hop, setHop] = useState<Hop>(null);
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
        if (!alive) return;
        setStatus(paired ? 'paired' : 'unpaired');
        if (paired && location.hostname !== NAME) void moveToName(() => alive, setHop);
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
  return { status, hop, recheck };
}

async function moveToName(alive: () => boolean, setHop: (hop: Hop) => void): Promise<void> {
  // A paired phone may read the pairing URL, key included: it is how it pairs under the name.
  const pairing = await fetchPairing().catch(() => null);
  const key = pairing?.url ? keyFromHash(new URL(pairing.url).hash) : null;
  if (!pairing?.name || !key) return; // no name announced (or `--local`)
  const url = `http://${pairing.name}/#k=${key}`;
  setHop({ state: 'trying' });
  let why: 'timeout' | 'refused' = 'timeout';
  for (let i = 0; i < TRIES && alive(); i++) {
    const result = await probe(pairing.name);
    if (result === 'ok') {
      location.replace(url);
      return;
    }
    why = result;
    if (why === 'refused') break; // refused at once: asking again changes nothing
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  if (alive()) setHop({ state: 'unreachable', why, url });
}

const ADDRESSES = 'nanar.addresses'; // localStorage: the PC's addresses, last seen
const FALLBACK_MS = 6000; // disconnected this long on nanar.local: try the addresses

/**
 * On nanar.local, keeps the PC's IP addresses, and moves back to the first that answers when
 * the name stops answering (a Wi-Fi that dropped and came back can leave it unheard for
 * minutes). The phone is paired there too: the QR code opened the page there first. Once the
 * name answers again, the page moves back to it on its own (`moveToName`).
 */
export function useAddressFallback(connected: boolean): void {
  useEffect(() => {
    if (!connected || location.hostname !== NAME) return;
    fetchPairing()
      .then((pairing) => {
        try {
          if (pairing.addresses.length)
            localStorage.setItem(ADDRESSES, JSON.stringify(pairing.addresses));
        } catch {
          // no storage (a private window): no fallback, nothing else lost
        }
      })
      .catch(() => {});
  }, [connected]);

  useEffect(() => {
    if (connected || location.hostname !== NAME) return;
    let addresses: string[] = [];
    try {
      addresses = JSON.parse(localStorage.getItem(ADDRESSES) ?? '[]') as string[];
    } catch {
      return;
    }
    if (!addresses.length) return;
    let alive = true;
    void (async () => {
      while (alive) {
        await new Promise((resolve) => setTimeout(resolve, FALLBACK_MS));
        for (const address of addresses) {
          if (!alive) return;
          if ((await probe(address)) === 'ok' && alive) {
            location.replace(`http://${address}${location.pathname}`);
            return;
          }
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [connected]);
}
