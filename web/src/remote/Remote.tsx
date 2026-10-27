import { useLocation } from 'wouter';

import { useLibrary, useLive } from '@/lib/api';

import { Controls, type Tab } from './Controls';
import { Library } from './Library';
import styles from './Remote.module.css';
import { usePairing, type Hop } from './usePairing';

/** The phone's page: pairing first, then the remote. */
export function Remote() {
  const { status, hop, recheck } = usePairing();

  if (status === 'paired') return <Paired hop={hop} onUnpaired={recheck} />;

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

function Paired({ hop, onUnpaired }: { hop: Hop; onUnpaired: () => void }) {
  const { state, connected } = useLive();
  const library = useLibrary(state?.libraryVersion);
  const [location, navigate] = useLocation();
  const tab: Tab = location.startsWith('/bibliotheque') ? 'library' : 'remote';
  return (
    <Controls
      state={state}
      connected={connected}
      hop={hop}
      tab={tab}
      onTab={(next) => navigate(next === 'library' ? '/bibliotheque' : '/')}
      onUnpaired={onUnpaired}
      library={(notify) => (
        <Library library={library} onStarted={() => navigate('/')} onError={notify} />
      )}
    />
  );
}
