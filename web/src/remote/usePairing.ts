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
 * answers, so that the pairing and the home screen icon outlive a change of network. A phone
 * paired before and arriving on an address it has no cookie for pairs with the key it kept.
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
        try {
          await pair(key);
        } catch (error) {
          if (error instanceof ApiError && error.code === 'wrong_key') {
            history.replaceState(null, '', location.pathname + location.search);
            if (alive) setStatus('wrong-key');
            return;
          }
          // The network, just after joining a Wi-Fi: the key stays, for the next try.
          if (!alive) return;
          setStatus('offline');
          retry = setTimeout(() => setAttempt((n) => n + 1), 3000);
          return;
        }
        // Out of the address bar (and of the history) once it has done its work.
        history.replaceState(null, '', location.pathname + location.search);
      }
      try {
        let paired = await isPaired();
        const known = remembered().key;
        if (!paired && known) {
          // Another address of the same Nanar (each has its own cookie): this phone was paired.
          paired = await pair(known).then(
            () => true,
            (error: unknown) => {
              if (error instanceof ApiError && error.code === 'wrong_key') forget();
              return false;
            },
          );
        }
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
  // Back from a fallback: the name will answer again sooner or later, and there is nothing to
  // say about it until then. Otherwise a few tries, then an offer to try by hand.
  const fellBack = remembered().fellBack;
  if (!fellBack) setHop({ state: 'trying' });
  let why: 'timeout' | 'refused' = 'timeout';
  for (let i = 0; (fellBack || i < TRIES) && alive(); i++) {
    const result = await probe(pairing.name);
    if (result === 'ok') {
      remember({ fellBack: false });
      location.replace(url);
      return;
    }
    why = result;
    if (!fellBack && why === 'refused') break; // refused at once: asking again changes nothing
    await new Promise((resolve) => setTimeout(resolve, fellBack ? FALLBACK_RETRY_MS : 1000));
  }
  if (alive()) setHop({ state: 'unreachable', why, url });
}

const REMEMBERED = 'nanar.remote'; // localStorage: how to reach Nanar when this address stops
const FALLBACK_MS = 6000; // disconnected this long: try the other ways to reach the PC
const FALLBACK_RETRY_MS = 20_000; // how often a page that fell back asks for the name again

interface Remembered {
  key: string | null;
  /** The PC's other ways in, "host:port": its name and its addresses, last seen. */
  hosts: string[];
  fellBack: boolean;
}

function remembered(): Remembered {
  try {
    const raw = JSON.parse(localStorage.getItem(REMEMBERED) ?? '{}') as Partial<Remembered>;
    return { key: raw.key ?? null, hosts: raw.hosts ?? [], fellBack: raw.fellBack ?? false };
  } catch {
    return { key: null, hosts: [], fellBack: false }; // no storage (a private window)
  }
}

function remember(changes: Partial<Remembered>): void {
  try {
    localStorage.setItem(REMEMBERED, JSON.stringify({ ...remembered(), ...changes }));
  } catch {
    // no storage: no fallback, nothing else lost
  }
}

function forget(): void {
  try {
    localStorage.removeItem(REMEMBERED);
  } catch {
    // nothing to forget then
  }
}

/** The address of `host` for this phone, on the same page, pairing it there with `key`. */
export function fallbackUrl(host: string, path: string, key: string | null): string {
  return `http://${host}${path}${key ? `#k=${key}` : ''}`;
}

/**
 * Keeps the PC's other ways in (its name, its addresses, and the key, as each has its own cookie),
 * and moves to the first that answers when this one stops: a Wi-Fi that dropped and came back can
 * leave nanar.local unheard for minutes, and the PC's address changes with the network. Once the
 * name answers again, the page moves back to it (`moveToName`).
 */
export function useAddressFallback(connected: boolean): void {
  useEffect(() => {
    if (!connected) return;
    fetchPairing()
      .then((pairing) => {
        const key = pairing.url ? keyFromHash(new URL(pairing.url).hash) : null;
        const hosts = pairing.name ? [pairing.name, ...pairing.addresses] : pairing.addresses;
        if (hosts.length) remember({ key, hosts });
      })
      .catch(() => {});
  }, [connected]);

  useEffect(() => {
    if (connected) return;
    const { key, hosts } = remembered();
    const others = hosts.filter((host) => host !== location.host);
    if (!others.length) return;
    let alive = true;
    void (async () => {
      while (alive) {
        await new Promise((resolve) => setTimeout(resolve, FALLBACK_MS));
        for (const host of others) {
          if (!alive) return;
          if ((await probe(host)) === 'ok' && alive) {
            remember({ fellBack: !host.startsWith(`${NAME}:`) });
            location.replace(fallbackUrl(host, location.pathname, key));
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
