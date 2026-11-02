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
  failed:
    'Windows n’a pas voulu ouvrir le Wi-Fi. Réessaie, ou ouvre-le dans Paramètres › Réseau et Internet › Point d’accès sans fil mobile.',
};

const POLL_MS = 20_000; // Windows closes a hotspot nobody uses, and has its own switch

/** When the phone doesn't reach Nanar: what to check, and mode hôtel, the PC's own Wi-Fi. */
export function Hotel({
  hotspot,
  playing,
  onBack,
}: {
  hotspot: State['hotspot'];
  playing: boolean;
  onBack: () => void;
}) {
  const [passphrase, setPassphrase] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pairing, setPairing] = useState<Pairing | null>(null);

  useEffect(() => {
    if (playing) return; // this page is hidden under the film: nothing to keep up to date
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // One question at a time: PowerShell can take ten seconds to answer.
    const load = async () => {
      await fetchPairing()
        .then((p) => alive && setPairing(p))
        .catch(() => {});
      await fetchHotspot()
        .then((answer) => alive && setPassphrase(answer.passphrase))
        .catch(() => {}); // the live state brings the rest
      if (alive) timer = setTimeout(() => void load(), POLL_MS);
    };
    void load();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [playing]);

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
    <section aria-labelledby="hotel-title" className={styles.page} data-careful>
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
                {passphrase && ` Ou à la main : mot de passe ${passphrase}.`}
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
            Nanar le ferme en se fermant, s’il l’a ouvert lui-même. Windows le ferme aussi tout seul
            si aucun appareil ne s’y connecte pendant quelques minutes.
          </p>
        </>
      ) : (
        <>
          <div className={styles.step} data-wide>
            {remote}
            <div>
              <p className={styles.settingTitle}>
                Scanne ce code avec l’appareil photo du téléphone.
              </p>
              <p className={styles.note}>Rien ne s’ouvre ?</p>
              <ul className={styles.checks}>
                <li>
                  Le téléphone doit être connecté au même réseau que le PC (sa box, pas la 4G ou la
                  5G).
                </li>
                <li>
                  Pare-feu : dans le menu Démarrer, tape « pare-feu », ouvre « Autoriser une
                  application via le Pare-feu Windows », et coche Nanar pour les réseaux privés et
                  publics.
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
            data-checking={!hotspot.checked || undefined}
            onClick={() => turn(true)}
          >
            {busy ? 'Ouverture… (Windows peut prendre une minute)' : 'Ouvrir un Wi-Fi Nanar'}
          </button>
          {!hotspot.available && !error && (
            <p className={styles.note}>
              {hotspot.checked
                ? MESSAGES[hotspot.code ?? 'unavailable']
                : 'Nanar demande à Windows si ce PC peut ouvrir un Wi-Fi…'}
            </p>
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
