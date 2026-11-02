import { useEffect, useState } from 'react';

import { fetchPairing, type Pairing } from '@/lib/api';

import styles from './RemoteCard.module.css';

const REFRESH_MS = 30_000; // the PC may change networks (a hotel, a phone's hotspot)
const PAIRED_BEFORE = 'nanar.phoneSeen'; // localStorage: a phone has come at least once
const BLOCKED =
  'Le pare-feu de Windows semble bloquer les téléphones : « Connecter un téléphone ».';

function pairedBefore(): boolean {
  try {
    return localStorage.getItem(PAIRED_BEFORE) !== null;
  } catch {
    return false;
  }
}

/** The QR code that turns a phone into the remote; a single line once one has come, as a phone
 *  gone to sleep shouldn't bring a big code back over the library every evening. */
export function RemoteCard({
  phones,
  wifi,
  firewallBlocks,
}: {
  phones: number;
  wifi: string | null;
  firewallBlocks: string | null;
}) {
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [seen, setSeen] = useState(pairedBefore);

  useEffect(() => {
    let alive = true;
    const load = () =>
      fetchPairing()
        .then((p) => alive && setPairing(p))
        .catch(() => {});
    void load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (phones === 0 || seen) return;
    try {
      localStorage.setItem(PAIRED_BEFORE, '1');
    } catch {
      // the big code again next time, nothing else lost
    }
    const timer = setTimeout(() => setSeen(true), 0);
    return () => clearTimeout(timer);
  }, [phones, seen]);

  if (!pairing) return null;

  const blocked = firewallBlocks !== null && phones === 0;

  if (!pairing.lan || !pairing.url) {
    return (
      <aside className={styles.card} data-compact>
        <p className={styles.title}>Télécommande</p>
        <p className={styles.text}>
          {pairing.lan ? 'Pas de réseau : connecte le PC au Wi-Fi.' : 'Désactivée (--local).'}
        </p>
      </aside>
    );
  }

  if (seen || phones > 0) {
    return (
      <aside className={styles.card} data-compact>
        <p className={styles.text}>
          {phones === 0
            ? 'Télécommande : aucun téléphone en ce moment.'
            : phones > 1
              ? `${phones} téléphones connectés.`
              : '1 téléphone connecté.'}
          {wifi && ` Wi-Fi « ${wifi} ».`}
        </p>
        {blocked && <p className={styles.text}>{BLOCKED}</p>}
      </aside>
    );
  }

  return (
    <aside className={styles.card}>
      {/* The address is in the query so that the image changes with the network. */}
      <img
        className={styles.qr}
        src={`/api/pairing/qr.svg?for=${encodeURIComponent(pairing.addresses[0] ?? '')}`}
        alt="QR code de la télécommande"
      />
      <div className={styles.body}>
        <p className={styles.title}>Ton téléphone est la télécommande</p>
        <p className={styles.text}>
          Scanne ce code avec l’appareil photo du téléphone, connecté au même réseau que le PC.
        </p>
        <p className={styles.text}>
          {blocked ? BLOCKED : 'Rien ne s’ouvre ? « Connecter un téléphone », en haut.'}
        </p>
        {wifi && <p className={styles.text}>Sur le Wi-Fi « {wifi} » (mode hôtel).</p>}
      </div>
    </aside>
  );
}
