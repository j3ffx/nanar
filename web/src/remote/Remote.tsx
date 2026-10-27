import { useLive } from '@/lib/api';

import { Controls } from './Controls';
import styles from './Remote.module.css';
import { usePairing } from './usePairing';

/** The phone's page: pairing first, then the remote. */
export function Remote() {
  const { status, recheck } = usePairing();

  if (status === 'paired') return <Paired onUnpaired={recheck} />;

  return (
    <main className={styles.gate}>
      <p className={styles.logo}>
        Nanar<span className={styles.dot}>.</span>
      </p>
      {status === 'checking' && <p className={styles.lead}>Connexion à Nanar…</p>}
      {status === 'offline' && (
        <>
          <p className={styles.lead}>Nanar ne répond pas.</p>
          <p className={styles.hint}>
            Vérifie qu’il est ouvert sur l’ordinateur, et que ton téléphone est sur le même Wi-Fi.
          </p>
        </>
      )}
      {(status === 'unpaired' || status === 'wrong-key') && (
        <>
          <p className={styles.lead}>
            {status === 'wrong-key'
              ? 'Ce QR code n’est plus le bon.'
              : 'Ce téléphone n’est pas encore la télécommande.'}
          </p>
          <p className={styles.hint}>
            Scanne le QR code affiché sur la télé avec l’appareil photo de ton téléphone.
          </p>
        </>
      )}
    </main>
  );
}

function Paired({ onUnpaired }: { onUnpaired: () => void }) {
  const { state, connected } = useLive();
  return <Controls state={state} connected={connected} onUnpaired={onUnpaired} />;
}
