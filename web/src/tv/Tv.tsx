import { useEffect, useRef, useState } from 'react';
import { Route, Switch, useLocation } from 'wouter';

import { command, useLibrary, useLive } from '@/lib/api';
import { isFiltered, NO_FILTER, type Filter } from '@/lib/filter';
import { DIRECTIONS, moveFocus } from '@/lib/spatial';

import { Backdrop } from './Backdrop';
import { GroupPage } from './GroupPage';
import { Header } from './Header';
import { Home } from './Home';
import { RemoteCard } from './RemoteCard';
import styles from './Tv.module.css';
import { useIdle } from './useIdle';

const DIM_AFTER_MS = 4 * 60 * 1000;

function findItem(root: HTMLElement | null, id: string | null): HTMLElement | null {
  return id ? (root?.querySelector<HTMLElement>(`[data-id="${CSS.escape(id)}"]`) ?? null) : null;
}

/** Focuses an item (or the first one), in the middle of the screen. */
function putForward(root: HTMLElement | null, id: string | null): void {
  const target = findItem(root, id) ?? root?.querySelector<HTMLElement>('[data-nav]');
  target?.focus();
  target?.scrollIntoView({ block: 'center', behavior: 'smooth' });
}

/** The TV page, shown in Nanar's window: the library, browsed with the arrows or the mouse. */
export function Tv() {
  const { state } = useLive();
  const library = useLibrary(state?.libraryVersion);
  const [location, navigate] = useLocation();
  const main = useRef<HTMLElement>(null);
  const idle = useIdle(DIM_AFTER_MS);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>(NO_FILTER);

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
        } else if (isFiltered(filter)) {
          event.preventDefault();
          setFilter(NO_FILTER); // back to the whole library
        } else if (event.key === 'Escape' && state?.fullscreen) {
          command('fullscreen', false).catch(() => {});
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [location, navigate, state?.fullscreen, filter]);

  // The TV follows what a phone looks at: its page, and the film it picked. Not on first load
  // (the TV opens on its own home), only when a phone moves.
  const followed = useRef<number | null>(null);
  const pending = useRef<string | null>(null); // the item to put forward once its page shows
  const view = state?.view;
  useEffect(() => {
    if (!view) return;
    if (followed.current === null || view.seq === followed.current) {
      followed.current = view.seq;
      return;
    }
    followed.current = view.seq;
    setFilter(view.filter);
    if (view.path !== location) {
      pending.current = view.focus ?? '';
      navigate(view.path);
    } else {
      putForward(main.current, view.focus);
    }
  }, [view, location, navigate]);

  // Back from a saga, its card has the focus again; otherwise the first card takes it, so that
  // the arrows work straight away.
  const lastGroup = useRef<string | null>(null);
  useEffect(() => {
    if (!library || !main.current) return;
    const opened = /^\/g\/([^/]+)/.exec(location)?.[1];
    if (opened) lastGroup.current = opened;
    if (pending.current !== null) {
      putForward(main.current, pending.current);
      pending.current = null;
      return;
    }
    if (main.current.contains(document.activeElement)) return;
    const back = location === '/' ? findItem(main.current, lastGroup.current) : null;
    (back ?? main.current.querySelector<HTMLElement>('[data-nav]'))?.focus();
  }, [library, location, filter]);

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
              <Home
                library={library}
                filter={filter}
                offerIntegration={!!state?.offerIntegration}
                onError={onError}
              />
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
        {(location !== '/' || isFiltered(filter)) && (
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
