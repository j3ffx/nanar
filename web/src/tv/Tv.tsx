import { useCallback, useEffect, useRef, useState } from 'react';
import { Route, Switch, useLocation } from 'wouter';

import { command, useLibrary, useLive } from '@/lib/api';
import { isFiltered, NO_FILTER, type Filter } from '@/lib/filter';
import { DIRECTIONS, moveFocus, scrollBehavior } from '@/lib/spatial';

import { Backdrop } from './Backdrop';
import { GroupPage } from './GroupPage';
import { Header } from './Header';
import { Home } from './Home';
import { Hotel } from './Hotel';
import { KeyHelp } from './KeyHelp';
import { RemoteCard } from './RemoteCard';
import { Settings } from './Settings';
import styles from './Tv.module.css';
import { useIdle } from './useIdle';

const DIM_AFTER_MS = 4 * 60 * 1000;

const NOTICES: Record<string, string> = {
  cannot_play: 'Impossible de lire cette vidéo : le fichier a peut-être été déplacé.',
  quota_reached: 'Plus de sous-titres en ligne pour aujourd’hui (limite d’OpenSubtitles).',
};

function findItem(root: HTMLElement | null, id: string | null): HTMLElement | null {
  return id ? (root?.querySelector<HTMLElement>(`[data-id="${CSS.escape(id)}"]`) ?? null) : null;
}

/** Where a page starts: its "resume" row, its first card; a page of text, whatever it offers. */
function firstItem(root: HTMLElement | null): HTMLElement | null {
  return (
    root?.querySelector<HTMLElement>('[data-resume]') ??
    root?.querySelector<HTMLElement>('main [data-nav]:not([data-back]):not(:disabled)') ??
    root?.querySelector<HTMLElement>('main [data-nav]:not(:disabled)') ??
    null
  );
}

/** Focuses an item (or the first one), in the middle of the screen. */
function putForward(root: HTMLElement | null, id: string | null): void {
  const target = findItem(root, id) ?? firstItem(root);
  target?.focus();
  target?.scrollIntoView({ block: 'center', behavior: scrollBehavior() });
}

/** The pages of this machine: a phone browsing the library doesn't take the TV away from them. */
const isOwnPage = (path: string) => path.startsWith('/hotel') || path.startsWith('/reglages');

/** The TV page, shown in Nanar's window: the library, browsed with the arrows or the mouse. */
export function Tv() {
  const { state } = useLive();
  const library = useLibrary(state?.libraryVersion);
  const [location, navigate] = useLocation();
  const root = useRef<HTMLDivElement>(null);
  const main = useRef<HTMLElement>(null);
  // Someone on the sofa never touches the PC: what the phones do counts as much as the mouse.
  const activity = `${state?.view.seq}/${state?.phones}/${state?.libraryVersion}/${!!state?.playing}`;
  const idle = useIdle(DIM_AFTER_MS, activity);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>(NO_FILTER);

  /** Up one level: from a help page to the settings, from any other page to the library, from
   *  search results to the whole library. */
  const back = useCallback((): boolean => {
    if (location.startsWith('/reglages/')) navigate('/reglages');
    else if (location !== '/') navigate('/');
    else if (isFiltered(filter)) setFilter(NO_FILTER);
    else return false;
    return true;
  }, [location, navigate, filter]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      // Typing in a field (a key, in the settings): its keys are its own, up and down aside.
      const typing = event.target instanceof HTMLInputElement && event.target.type !== 'checkbox';
      if (typing && !['ArrowUp', 'ArrowDown', 'Escape'].includes(event.key)) return;
      const direction = DIRECTIONS[event.key];
      if (direction && root.current) {
        if (moveFocus(root.current, direction)) event.preventDefault();
        return;
      }
      if (event.key === 'f' || event.key === 'F') {
        event.preventDefault();
        command('fullscreen').catch(() => setError('Impossible de passer en plein écran.'));
      } else if (event.key === 'Escape' || event.key === 'Backspace') {
        if (back()) {
          event.preventDefault();
        } else if (event.key === 'Escape' && state?.fullscreen) {
          command('fullscreen', false).catch(() => {});
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [back, state?.fullscreen]);

  // The TV follows what a phone looks at: its page, and the film it picked. Not on first load
  // (the TV opens on its own home), only when a phone moves.
  const followed = useRef<number | null>(null);
  const pending = useRef<string | null>(null); // the item to put forward once its page shows
  const view = state?.view;
  useEffect(() => {
    if (!view) return;
    if (followed.current === null || view.seq === followed.current || isOwnPage(location)) {
      followed.current = view.seq;
      return;
    }
    followed.current = view.seq;
    setFilter(view.filter);
    if (view.path !== location) {
      pending.current = view.focus ?? '';
      navigate(view.path);
    } else {
      putForward(root.current, view.focus);
    }
  }, [view, location, navigate]);

  // Back from a page, what opened it has the focus again; otherwise the first card takes it, so
  // that the arrows work straight away.
  const cameFrom = useRef<string | null>(null);
  useEffect(() => {
    if (!library || !root.current) return;
    const opened = /^\/g\/([^/]+)/.exec(location)?.[1];
    if (opened) cameFrom.current = opened;
    if (location === '/hotel') cameFrom.current = 'open-phone';
    if (location.startsWith('/reglages')) cameFrom.current = 'open-settings';
    if (pending.current !== null) {
      putForward(root.current, pending.current);
      pending.current = null;
      return;
    }
    if (main.current?.contains(document.activeElement)) return;
    const previous = location === '/' ? findItem(root.current, cameFrom.current) : null;
    // Not scrolled: the top of the page, its first heading, stays in sight.
    (previous ?? firstItem(root.current))?.focus({ preventScroll: !previous });
  }, [library, location, filter]);

  const onError = useCallback((message: string) => {
    setError(message);
    setTimeout(() => setError(null), 5000);
  }, []);

  // What went wrong on its own (a video that can't play), once.
  const noticed = useRef<number | null>(null);
  const notice = state?.notice;
  useEffect(() => {
    if (!notice || noticed.current === notice.seq) return;
    const first = noticed.current === null && !state?.playing;
    noticed.current = notice.seq;
    if (!first) onError(NOTICES[notice.code] ?? 'Quelque chose n’a pas marché.');
  }, [notice, state?.playing, onError]);

  const library_ = library;
  const dim = idle && !state?.playing && (state?.phones ?? 0) > 0;
  const ownPage = isOwnPage(location);

  return (
    <div ref={root} className={styles.tv} data-dim={dim ? 'true' : undefined}>
      <Backdrop />
      <Header demo={state?.demo ?? false} onNavigate={navigate} />
      <main ref={main} className={styles.main}>
        {library_ === null ? (
          <p className={styles.loading}>Les bobines arrivent…</p>
        ) : (
          <Switch>
            <Route path="/hotel">
              <Hotel
                hotspot={state?.hotspot ?? { available: false, on: false, ssid: null, code: null }}
                onBack={back}
              />
            </Route>
            <Route path="/reglages/:service">
              {(params) => (
                <KeyHelp
                  service={params.service === 'tmdb' ? 'tmdb' : 'opensubtitles'}
                  onBack={back}
                />
              )}
            </Route>
            <Route path="/reglages">
              <Settings updates={state?.updates ?? null} onBack={back} onNavigate={navigate} />
            </Route>
            <Route path="/g/:id">
              {(params) => (
                <GroupPage library={library_} groupId={params.id} onBack={back} onError={onError} />
              )}
            </Route>
            <Route>
              <Home
                library={library_}
                filter={filter}
                onBack={back}
                update={state?.updates?.supported ? state.updates : null}
                offerIntegration={!!state?.offerIntegration}
                onError={onError}
              />
            </Route>
          </Switch>
        )}
      </main>
      <footer className={styles.hints} aria-hidden="true">
        <span>
          <kbd>↵</kbd> {ownPage ? 'Valider' : 'Lancer'}
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
      {!ownPage && (
        <RemoteCard
          phones={state?.phones ?? 0}
          wifi={state?.hotspot.on ? state.hotspot.ssid : null}
        />
      )}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
