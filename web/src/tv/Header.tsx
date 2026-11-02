import { useEffect, useState } from 'react';

import styles from './Header.module.css';

// What the marquee says, in turn.
const TAGLINES = [
  'Ce soir, on ose.',
  'Un nanar, c’est un navet qu’on aime.',
  'Popcorn non fourni.',
  'Ne quittez pas votre canapé.',
  'Effets spéciaux garantis d’époque.',
];

const TAGLINE_MS = 12_000;

function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 10_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

export function Header({
  demo,
  onNavigate,
}: {
  demo: boolean;
  onNavigate: (path: string) => void;
}) {
  const now = useNow();
  const [line, setLine] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setLine((n) => (n + 1) % TAGLINES.length), TAGLINE_MS);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className={styles.header}>
      <div className={styles.brand}>
        <h1 className={styles.logo}>
          Nanar<span className={styles.dot}>.</span>
        </h1>
        <p key={line} className={styles.tagline}>
          {TAGLINES[line]}
        </p>
      </div>
      <div className={styles.side}>
        {demo && <span className={styles.demo}>Démo</span>}
        <button
          type="button"
          data-nav
          data-id="open-phone"
          className={styles.link}
          onClick={() => onNavigate('/hotel')}
        >
          Connecter un téléphone
        </button>
        <button
          type="button"
          data-nav
          data-id="open-settings"
          className={styles.link}
          onClick={() => onNavigate('/reglages')}
        >
          Réglages
        </button>
        <time className={styles.clock} dateTime={now.toISOString()}>
          {now.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
        </time>
      </div>
    </header>
  );
}
