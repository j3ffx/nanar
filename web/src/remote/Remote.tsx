import { useLiveState } from '@/lib/api';

import styles from './Remote.module.css';

/** The phone's page. Pairing and the controls come next; for now it says what plays. */
export function Remote() {
  const state = useLiveState();
  return (
    <main className={styles.page}>
      <h1 className={styles.logo}>Nanar</h1>
      <p className={styles.status}>
        {state === null
          ? 'Connexion à Nanar…'
          : state.playing
            ? `À l’écran : ${state.playing.video.title}`
            : 'Rien à l’écran pour l’instant.'}
      </p>
      <p className={styles.note}>La télécommande arrive bientôt.</p>
    </main>
  );
}
