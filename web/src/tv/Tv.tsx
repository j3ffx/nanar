import { useEffect, useRef, useState } from 'react';
import { Route, Switch, useLocation } from 'wouter';

import { command, useLibrary, useLive } from '@/lib/api';
import { DIRECTIONS, moveFocus } from '@/lib/spatial';

import { Backdrop } from './Backdrop';
import { GroupPage } from './GroupPage';
import { Header } from './Header';
import { Home } from './Home';
import { RemoteCard } from './RemoteCard';
import styles from './Tv.module.css';
import { useIdle } from './useIdle';

const DIM_AFTER_MS = 4 * 60 * 1000;

/** The TV page, shown in Nanar's window: the library, browsed with the arrows or the mouse. */
export function Tv() {
  const library = useLibrary();
  const { state } = useLive();
  const [location, navigate] = useLocation();
  const main = useRef<HTMLElement>(null);
  const idle = useIdle(DIM_AFTER_MS);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const direction = DIRECTIONS[event.key];
      if (direction && main.current) {
        if (moveFocus(main.current, direction)) event.preventDefault();
        return;
      }
      if (event.key === 'f' || event.key === 'F') {
        event.preventDefault();
        command('fullscreen').catch(() => setError('Impossible de passer en plein écran.'));
      } else if (event.key === 'Escape' || event.key === 'Backspace') {
        if (location !== '/') {
          event.preventDefault();
          navigate('/');
        } else if (event.key === 'Escape' && state?.fullscreen) {
          command('fullscreen', false).catch(() => {});
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [location, navigate, state?.fullscreen]);

  // Back from a saga, its card has the focus again; otherwise the first card takes it, so that
  // the arrows work straight away.
  const lastGroup = useRef<string | null>(null);
  useEffect(() => {
    if (!library || !main.current) return;
    const opened = /^\/g\/([^/]+)/.exec(location)?.[1];
    if (opened) lastGroup.current = opened;
    if (main.current.contains(document.activeElement)) return;
    const back =
      location === '/' && lastGroup.current
        ? main.current.querySelector<HTMLElement>(`[data-id="${lastGroup.current}"]`)
        : null;
    (back ?? main.current.querySelector<HTMLElement>('[data-nav]'))?.focus();
  }, [library, location]);

  const onError = (message: string) => {
    setError(message);
    setTimeout(() => setError(null), 5000);
  };

  return (
    <div className={styles.tv} data-dim={idle && !state?.playing ? 'true' : undefined}>
      <Backdrop />
      <Header demo={state?.demo ?? false} />
      <main ref={main} className={styles.main}>
        {library === null ? (
          <p className={styles.loading}>Les bobines arrivent…</p>
        ) : (
          <Switch>
            <Route path="/g/:id">
              {(params) => <GroupPage library={library} groupId={params.id} onError={onError} />}
            </Route>
            <Route>
              <Home library={library} onError={onError} />
            </Route>
          </Switch>
        )}
      </main>
      <footer className={styles.hints} aria-hidden="true">
        <span>
          <kbd>↵</kbd> Lancer
        </span>
        <span>
          <kbd>F</kbd> Plein écran
        </span>
        {location !== '/' && (
          <span>
            <kbd>Échap</kbd> Retour
          </span>
        )}
      </footer>
      <RemoteCard phones={state?.phones ?? 0} />
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
