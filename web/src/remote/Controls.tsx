import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';

import { ApiError, command, type Playing, type State, type Track } from '@/lib/api';
import { clock, episodeCode } from '@/lib/format';

import * as Icon from './icons';
import styles from './Remote.module.css';
import { Sheet } from './Sheet';
import type { Hop } from './usePairing';

// What the phone says when Nanar refuses something.
const MESSAGES: Record<string, string> = {
  nothing_playing: 'Rien ne passe en ce moment.',
  no_neighbour: 'Pas d’autre épisode de ce côté.',
  bad_value: 'Nanar n’a pas compris.',
};

export type Tab = 'remote' | 'library';

interface Props {
  state: State | null;
  connected: boolean;
  hop: Hop;
  tab: Tab;
  onTab: (tab: Tab) => void;
  onUnpaired: () => void;
  /** The library tab's content, given a way to show a message. */
  library: (notify: (message: string) => void) => ReactNode;
}

export function Controls({ state, connected, hop, tab, onTab, onUnpaired, library }: Props) {
  const [toast, setToast] = useState<{ text: string } | null>(null);
  const notify = useCallback((text: string) => setToast({ text }), []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(timer);
  }, [toast]);

  const send = useCallback(
    (action: string, value?: unknown) => {
      navigator.vibrate?.(8);
      command(action, value).catch((error: unknown) => {
        if (error instanceof ApiError && error.code === 'pairing_required') {
          onUnpaired();
          return;
        }
        const code = error instanceof ApiError ? error.code : '';
        notify(MESSAGES[code] ?? 'Nanar ne répond pas.');
      });
    },
    [onUnpaired, notify],
  );

  const playing = state?.playing ?? null;

  return (
    <main className={styles.remote}>
      <header className={styles.top}>
        <p className={styles.logoSmall}>
          Nanar<span className={styles.dot}>.</span>
        </p>
        <span className={styles.link} data-on={connected || undefined}>
          {connected ? 'Connecté' : 'Connexion…'}
        </span>
        <button
          type="button"
          className={styles.iconButton}
          onClick={() => send('fullscreen')}
          aria-label={state?.fullscreen ? 'Quitter le plein écran' : 'Plein écran'}
          disabled={!state}
        >
          {state?.fullscreen ? <Icon.ExitFullscreen /> : <Icon.Fullscreen />}
        </button>
      </header>

      {state?.upNext && (
        <aside className={styles.upNext} aria-live="polite">
          <p className={styles.upNextText}>
            <span>
              À suivre dans <strong>{state.upNext.seconds} s</strong>
            </span>
            <span className={styles.upNextTitle}>
              {state.upNext.video.kind === 'episode'
                ? `${episodeCode(state.upNext.video)} ${state.upNext.video.episodeTitle ?? ''}`
                : state.upNext.video.title}
            </span>
          </p>
          <div className={styles.row}>
            <Pill onClick={() => send('next')}>
              <Icon.Next /> Maintenant
            </Pill>
            <Pill onClick={() => send('stop')} tone="stop">
              <Icon.Stop /> Arrêter
            </Pill>
          </div>
        </aside>
      )}

      {tab === 'library' ? (
        library(notify)
      ) : playing ? (
        <NowPlaying playing={playing} send={send} />
      ) : (
        <section className={styles.idle}>
          <p className={styles.lead}>{state ? 'Rien à l’écran.' : 'Connexion à Nanar…'}</p>
          <p className={styles.hint}>Choisis un film dans la bibliothèque, ou sur la télé.</p>
          <button type="button" className={styles.idleButton} onClick={() => onTab('library')}>
            Ouvrir la bibliothèque
          </button>
        </section>
      )}

      {hop?.state === 'unreachable' && (
        <aside className={styles.hop}>
          <p className={styles.note}>
            Pour que la télécommande marche sur tous les Wi-Fi, ouvre-la sous son nom fixe, puis
            ajoute-la à l’écran d’accueil.
            {hop.why === 'timeout' && ' (nanar.local n’a pas répondu tout de suite.)'}
          </p>
          <a className={styles.hopLink} href={hop.url}>
            Ouvrir nanar.local
          </a>
        </aside>
      )}

      {toast && (
        <p className={styles.toast} role="status">
          {toast.text}
        </p>
      )}

      <nav className={styles.tabs} aria-label="Pages">
        <button
          type="button"
          className={styles.tab}
          aria-current={tab === 'remote' ? 'page' : undefined}
          onClick={() => onTab('remote')}
        >
          <Icon.Play /> Télécommande
        </button>
        <button
          type="button"
          className={styles.tab}
          aria-current={tab === 'library' ? 'page' : undefined}
          onClick={() => onTab('library')}
        >
          <Icon.Grid /> Bibliothèque
        </button>
      </nav>
    </main>
  );
}

type Send = (action: string, value?: unknown) => void;

function NowPlaying({ playing, send }: { playing: Playing; send: Send }) {
  const [sheet, setSheet] = useState<'audio' | 'subs' | null>(null);
  const { video } = playing;

  return (
    <>
      <section className={styles.now} aria-live="polite">
        <p className={styles.kicker}>
          {video.kind === 'episode' ? episodeCode(video) : video.year ? String(video.year) : 'Film'}
        </p>
        <h1 className={styles.title}>
          {video.kind === 'episode' ? (video.episodeTitle ?? video.title) : video.title}
        </h1>
        {video.kind === 'episode' && <p className={styles.series}>{video.title}</p>}
        <Progress position={playing.position} duration={playing.duration} send={send} />
      </section>

      <section className={styles.pad} aria-label="Lecture">
        <Round label="Précédent" onClick={() => send('previous')} disabled={!playing.hasPrevious}>
          <Icon.Previous />
        </Round>
        <Round label="10 secondes en arrière" onClick={() => send('seek', -10)}>
          <Icon.Jump seconds={-10} />
        </Round>
        <Round label={playing.paused ? 'Lecture' : 'Pause'} onClick={() => send('pause')} big>
          {playing.paused ? <Icon.Play /> : <Icon.Pause />}
        </Round>
        <Round label="10 secondes en avant" onClick={() => send('seek', 10)}>
          <Icon.Jump seconds={10} />
        </Round>
        <Round label="Suivant" onClick={() => send('next')} disabled={!playing.hasNext}>
          <Icon.Next />
        </Round>
      </section>

      <section className={styles.row} aria-label="Déplacements">
        <Pill onClick={() => send('seek', -60)}>
          <Icon.Jump seconds={-60} /> 1 min
        </Pill>
        <Pill onClick={() => send('stop')} tone="stop">
          <Icon.Stop /> Arrêter
        </Pill>
        <Pill onClick={() => send('seek', 60)}>
          1 min <Icon.Jump seconds={60} />
        </Pill>
      </section>

      <VolumeBar volume={playing.volume} muted={playing.muted} send={send} />

      <section className={styles.row} aria-label="Pistes">
        <Pill onClick={() => setSheet('audio')} wide>
          <Icon.Speech />
          <span className={styles.pillText}>{selectedLabel(playing.audio) ?? 'Audio'}</span>
        </Pill>
        <Pill onClick={() => setSheet('subs')} wide>
          <Icon.Subtitles />
          <span className={styles.pillText}>
            {selectedLabel(playing.subs) ?? 'Sans sous-titres'}
          </span>
        </Pill>
      </section>

      <Sheet title="Audio" open={sheet === 'audio'} onClose={() => setSheet(null)}>
        <TrackList tracks={playing.audio} onPick={(id) => send('audio', id)} />
      </Sheet>
      <Sheet title="Sous-titres" open={sheet === 'subs'} onClose={() => setSheet(null)}>
        <TrackList tracks={playing.subs} onPick={(id) => send('sub', id)} none="Aucun" />
        <Stepper
          label="Décalage"
          value={`${playing.subDelay >= 0 ? '+' : '−'}${Math.abs(playing.subDelay).toFixed(1).replace('.', ',')} s`}
          onLess={() => send('sub_delay', round(playing.subDelay - 0.1))}
          onMore={() => send('sub_delay', round(playing.subDelay + 0.1))}
        />
        <Stepper
          label="Taille"
          value={`${Math.round(playing.subScale * 100)} %`}
          onLess={() => send('sub_scale', round(playing.subScale - 0.1))}
          onMore={() => send('sub_scale', round(playing.subScale + 0.1))}
        />
      </Sheet>
    </>
  );
}

const round = (n: number) => Math.round(n * 10) / 10;

function selectedLabel(tracks: Track[]): string | null {
  return tracks.find((t) => t.selected)?.label ?? null;
}

/**
 * Where the video is, and where to go: the bar follows the finger (the time it would jump to
 * shows big), and the video jumps there when the finger lifts.
 */
function Progress({
  position,
  duration,
  send,
}: {
  position: number;
  duration: number | null;
  send: Send;
}) {
  const [target, setTarget] = useState<number | null>(null);
  const shown = target ?? position;
  const ratio = duration ? Math.min(1, shown / duration) : 0;
  const commit = () => {
    if (target !== null) send('seek_to', target);
    setTarget(null);
  };
  return (
    <div className={styles.progress} data-seeking={target !== null || undefined}>
      {target !== null && <p className={styles.seekTo}>{clock(target)}</p>}
      <input
        type="range"
        className={styles.scrub}
        min={0}
        max={Math.max(1, Math.floor(duration ?? 0))}
        step={1}
        value={Math.floor(shown)}
        disabled={!duration}
        aria-label="Avancement"
        aria-valuetext={`${clock(shown)} sur ${duration ? clock(duration) : 'durée inconnue'}`}
        style={{ '--level': `${ratio * 100}%` } as CSSProperties}
        onChange={(event) => setTarget(Number(event.target.value))}
        onPointerUp={commit}
        onKeyUp={commit}
        onBlur={() => setTarget(null)}
      />
      <div className={styles.times}>
        <span>{clock(shown)}</span>
        <span>{duration ? `−${clock(duration - shown)}` : ''}</span>
      </div>
    </div>
  );
}

function VolumeBar({ volume, muted, send }: { volume: number; muted: boolean; send: Send }) {
  // The slider follows the finger, and Nanar a few times a second, not on every pixel.
  const [dragging, setDragging] = useState<number | null>(null);
  const last = useRef(0);
  useEffect(() => {
    if (dragging === null) return;
    const now = Date.now();
    if (now - last.current > 120) {
      last.current = now;
      send('volume', dragging);
    }
  }, [dragging, send]);

  const shown = dragging ?? volume;
  return (
    <section className={styles.volume} aria-label="Volume">
      <button
        type="button"
        className={styles.iconButton}
        onClick={() => send('mute')}
        aria-label={muted ? 'Remettre le son' : 'Couper le son'}
        aria-pressed={muted}
      >
        {muted ? <Icon.Muted /> : <Icon.Volume />}
      </button>
      <input
        type="range"
        min={0}
        max={130}
        step={1}
        value={Math.round(shown)}
        aria-label="Volume"
        aria-valuetext={`${Math.round(shown)} %`}
        className={styles.slider}
        style={{ '--level': `${(shown / 130) * 100}%` } as CSSProperties}
        onChange={(event) => setDragging(Number(event.target.value))}
        onPointerUp={() => {
          if (dragging !== null) send('volume', dragging);
          setDragging(null);
        }}
        onKeyUp={() => {
          if (dragging !== null) send('volume', dragging);
          setDragging(null);
        }}
      />
      <span className={styles.volumeValue}>{Math.round(shown)}</span>
    </section>
  );
}

function TrackList({
  tracks,
  onPick,
  none,
}: {
  tracks: Track[];
  onPick: (id: number | null) => void;
  none?: string;
}) {
  const anySelected = tracks.some((t) => t.selected);
  return (
    <ul className={styles.tracks}>
      {none && (
        <li>
          <button
            type="button"
            className={styles.track}
            aria-pressed={!anySelected}
            onClick={() => onPick(null)}
          >
            {none}
            {!anySelected && <Icon.Check />}
          </button>
        </li>
      )}
      {tracks.map((track) => (
        <li key={track.id}>
          <button
            type="button"
            className={styles.track}
            aria-pressed={track.selected}
            onClick={() => onPick(track.id)}
          >
            {track.label}
            {track.external && <span className={styles.external}>fichier à côté</span>}
            {track.selected && <Icon.Check />}
          </button>
        </li>
      ))}
      {tracks.length === 0 && !none && <li className={styles.hint}>Aucune piste.</li>}
    </ul>
  );
}

function Stepper(props: { label: string; value: string; onLess: () => void; onMore: () => void }) {
  return (
    <div className={styles.stepper}>
      <span className={styles.stepperLabel}>{props.label}</span>
      <button type="button" onClick={props.onLess} aria-label={`${props.label} : moins`}>
        −
      </button>
      <output className={styles.stepperValue}>{props.value}</output>
      <button type="button" onClick={props.onMore} aria-label={`${props.label} : plus`}>
        +
      </button>
    </div>
  );
}

function Round(props: {
  label: string;
  onClick: () => void;
  children: ReactNode;
  big?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className={props.big ? styles.roundBig : styles.round}
      aria-label={props.label}
      onClick={props.onClick}
      disabled={props.disabled}
    >
      {props.children}
    </button>
  );
}

function Pill(props: { onClick: () => void; children: ReactNode; tone?: 'stop'; wide?: boolean }) {
  return (
    <button
      type="button"
      className={styles.pill}
      data-tone={props.tone}
      data-wide={props.wide || undefined}
      onClick={props.onClick}
    >
      {props.children}
    </button>
  );
}
