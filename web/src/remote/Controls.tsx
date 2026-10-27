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

interface Props {
  state: State | null;
  connected: boolean;
  hop: Hop;
  onUnpaired: () => void;
}

export function Controls({ state, connected, hop, onUnpaired }: Props) {
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const send = useCallback(
    (action: string, value?: unknown) => {
      navigator.vibrate?.(8);
      command(action, value).catch((error: unknown) => {
        if (error instanceof ApiError && error.code === 'pairing_required') {
          onUnpaired();
          return;
        }
        const code = error instanceof ApiError ? error.code : '';
        setToast(MESSAGES[code] ?? 'Nanar ne répond pas.');
        clearTimeout(toastTimer.current);
        toastTimer.current = setTimeout(() => setToast(null), 3000);
      });
    },
    [onUnpaired],
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

      {playing ? (
        <NowPlaying playing={playing} send={send} />
      ) : (
        <section className={styles.idle}>
          <p className={styles.lead}>{state ? 'Rien à l’écran.' : 'Connexion à Nanar…'}</p>
          <p className={styles.hint}>
            Choisis un film sur la télé. Bientôt, tu pourras aussi parcourir ta bibliothèque d’ici.
          </p>
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
          {toast}
        </p>
      )}
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
        <Progress position={playing.position} duration={playing.duration} />
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

function Progress({ position, duration }: { position: number; duration: number | null }) {
  const ratio = duration ? Math.min(1, position / duration) : 0;
  return (
    <div className={styles.progress}>
      <div
        className={styles.bar}
        role="progressbar"
        aria-label="Avancement"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration ?? 0)}
        aria-valuenow={Math.round(position)}
        aria-valuetext={`${clock(position)} sur ${duration ? clock(duration) : 'durée inconnue'}`}
      >
        <div className={styles.fill} style={{ width: `${ratio * 100}%` }} />
      </div>
      <div className={styles.times}>
        <span>{clock(position)}</span>
        <span>{duration ? `−${clock(duration - position)}` : ''}</span>
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
