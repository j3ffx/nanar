import { useEffect, useState } from 'react';

import { fetchPairing, type Pairing } from '@/lib/api';

import styles from './RemoteCard.module.css';

const REFRESH_MS = 30_000; // the PC may change networks (a hotel, a phone's hotspot)

/** The QR code that turns a phone into the remote, and how many phones already are. */
export function RemoteCard({ phones }: { phones: number }) {
  const [pairing, setPairing] = useState<Pairing | null>(null);

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

  if (!pairing) return null;

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

  const [main, ...others] = pairing.addresses;
  return (
    <aside className={styles.card} data-compact={phones > 0 || undefined}>
      {/* The URL is in the query so that the image changes with the network. */}
      <img
        className={styles.qr}
        src={`/api/pairing/qr.svg?for=${encodeURIComponent(pairing.url)}`}
        alt="QR code de la télécommande"
      />
      <div className={styles.body}>
        <p className={styles.title}>
          {phones > 0
            ? phones > 1
              ? `${phones} téléphones connectés`
              : '1 téléphone connecté'
            : 'Ton téléphone est la télécommande'}
        </p>
        <p className={styles.text}>
          {phones > 0 ? 'Un autre ? Scanne le code.' : 'Scanne ce code avec son appareil photo.'}
        </p>
        <p className={styles.address}>
          {main}
          {others.length > 0 && <span className={styles.others}> · ou {others.join(' · ')}</span>}
        </p>
      </div>
    </aside>
  );
}
