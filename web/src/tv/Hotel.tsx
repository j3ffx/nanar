import { useEffect, useState } from 'react';

import {
  ApiError,
  fetchHotspot,
  fetchPairing,
  turnHotspot,
  type Pairing,
  type State,
} from '@/lib/api';

import { BackButton } from './BackButton';
import styles from './Tv.module.css';

const MESSAGES: Record<string, string> = {
  no_internet:
    'Windows ne partage un Wi-Fi que si le PC a une connexion à Internet : connecte-le au Wi-Fi de l’hôtel (ou à un câble), puis réessaie.',
  unavailable: 'Ce PC ne sait pas ouvrir de Wi-Fi, ou Windows l’interdit sur ce réseau.',
  failed: 'Windows n’a pas voulu ouvrir le Wi-Fi. Réessaie, ou ouvre-le dans ses paramètres.',
};

const POLL_MS = 5000; // Windows closes a hotspot nobody uses, and has its own switch

/** When the phone doesn't reach Nanar: what to check, and mode hôtel, the PC's own Wi-Fi. */
export function Hotel({ hotspot, onBack }: { hotspot: State['hotspot']; onBack: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pairing, setPairing] = useState<Pairing | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      fetchPairing()
        .then((p) => alive && setPairing(p))
        .catch(() => {});
      fetchHotspot().catch(() => {}); // the live state brings the answer
    };
    load();
    const timer = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

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

  const remote = pairing?.url && (
    <img
      className={styles.stepQr}
      src={`/api/pairing/qr.svg?for=${encodeURIComponent(pairing.addresses[0] ?? '')}`}
      alt="QR code de la télécommande"
    />
  );

  return (
    <section aria-labelledby="hotel-title" className={styles.page}>
      <BackButton onBack={onBack} />
      <h2 id="hotel-title" className={styles.groupTitle}>
        Connecter le téléphone
      </h2>
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
            {remote && (
              <li className={styles.step}>
                {remote}
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
            {busy ? 'Fermeture…' : 'Fermer ce Wi-Fi'}
          </button>
          <p className={styles.note}>
            Il se ferme aussi quand tu fermes Nanar, et Windows le ferme tout seul si aucun appareil
            ne s’y connecte pendant quelques minutes.
          </p>
        </>
      ) : (
        <>
          <div className={styles.step} data-wide>
            {remote}
            <div>
              <p className={styles.settingTitle}>Rien ne s’ouvre après avoir scanné ?</p>
              <ul className={styles.checks}>
                <li>Le téléphone et le PC doivent être sur le même Wi-Fi.</li>
                <li>
                  Pare-feu : quand Windows a posé la question, il fallait autoriser Nanar. Vérifie
                  dans « Pare-feu Windows › Autoriser une application » que Nanar est coché pour les
                  réseaux privés et publics.
                </li>
                <li>Certains Wi-Fi, surtout à l’hôtel, isolent les appareils : voici la parade.</li>
              </ul>
            </div>
          </div>
          <h3 className={styles.settingTitle}>Mode hôtel</h3>
          <p className={styles.lead}>
            Nanar ouvre un Wi-Fi à lui, que ton téléphone rejoint d’un scan. Le PC reste connecté à
            Internet et partage sa connexion.
          </p>
          <button
            type="button"
            data-nav
            className={styles.action}
            disabled={busy || !hotspot.available}
            onClick={() => turn(true)}
          >
            {busy ? 'Ouverture…' : 'Ouvrir un Wi-Fi Nanar'}
          </button>
          {!hotspot.available && !error && (
            <p className={styles.note}>{MESSAGES[hotspot.code ?? 'no_internet']}</p>
          )}
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
