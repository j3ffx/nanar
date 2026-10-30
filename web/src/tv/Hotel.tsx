import { useEffect, useState } from 'react';

import { ApiError, fetchPairing, turnHotspot, type Pairing, type State } from '@/lib/api';

import { BackButton } from './BackButton';
import styles from './Tv.module.css';

const MESSAGES: Record<string, string> = {
  no_internet: 'Il faut au PC une connexion à partager (le Wi-Fi de l’hôtel, ou un câble).',
  unavailable: 'Ce PC ne sait pas ouvrir de Wi-Fi (ou Windows l’interdit ici).',
  failed: 'Windows n’a pas voulu ouvrir le Wi-Fi. Réessaie, ou ouvre-le dans ses paramètres.',
};

/** Mode hôtel: the PC opens a Wi-Fi of its own, which the phone joins in one scan. */
export function Hotel({ hotspot, onBack }: { hotspot: State['hotspot']; onBack: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pairing, setPairing] = useState<Pairing | null>(null);

  // The remote's address changes once the phone is on the PC's Wi-Fi: ask again then.
  useEffect(() => {
    let alive = true;
    fetchPairing()
      .then((p) => alive && setPairing(p))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [hotspot.on]);

  const turn = (on: boolean) => {
    setBusy(true);
    setError(null);
    turnHotspot(on)
      .catch((e: unknown) => {
        const code = e instanceof ApiError ? e.code : 'failed';
        setError(MESSAGES[code] ?? MESSAGES.failed!);
      })
      .finally(() => setBusy(false));
  };

  return (
    <section aria-labelledby="hotel-title" className={styles.page}>
      <BackButton onBack={onBack} />
      <h2 id="hotel-title" className={styles.groupTitle}>
        Mode hôtel
      </h2>
      <p className={styles.lead}>
        Le Wi-Fi d’un hôtel isole souvent les appareils : le téléphone ne voit pas le PC. Nanar peut
        ouvrir un Wi-Fi à lui, que ton téléphone rejoint d’un scan ; le PC garde sa connexion et la
        partage.
      </p>
      {hotspot.on ? (
        <>
          <ol className={styles.steps}>
            <li className={styles.step}>
              <img
                className={styles.stepQr}
                src={`/api/hotspot/qr.svg?ssid=${encodeURIComponent(hotspot.ssid ?? '')}`}
                alt="QR code du Wi-Fi de Nanar"
              />
              <p>
                <strong>1.</strong> Rejoins le Wi-Fi « {hotspot.ssid} » : scanne ce code avec
                l’appareil photo du téléphone.
              </p>
            </li>
            {pairing?.url && (
              <li className={styles.step}>
                <img
                  className={styles.stepQr}
                  src={`/api/pairing/qr.svg?for=${encodeURIComponent(pairing.url)}`}
                  alt="QR code de la télécommande"
                />
                <p>
                  <strong>2.</strong> Puis ouvre la télécommande avec celui-ci.
                </p>
              </li>
            )}
          </ol>
          <button
            type="button"
            data-nav
            className={styles.action}
            disabled={busy}
            onClick={() => turn(false)}
          >
            {busy ? 'Fermeture…' : 'Fermer le Wi-Fi de Nanar'}
          </button>
          <p className={styles.note}>Nanar le referme aussi en partant.</p>
        </>
      ) : (
        <>
          <button
            type="button"
            data-nav
            className={styles.action}
            disabled={busy || !hotspot.available}
            onClick={() => turn(true)}
          >
            {busy ? 'Ouverture…' : 'Ouvrir le Wi-Fi de Nanar'}
          </button>
          {!hotspot.available && !error && <p className={styles.note}>{MESSAGES.no_internet}</p>}
        </>
      )}
      {error && (
        <p className={styles.note} role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
