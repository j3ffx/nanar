import { useEffect, useState, type CSSProperties } from 'react';
import { Link, useLocation, useRoute } from 'wouter';

import { play, setView, type Library as LibraryData, type Video } from '@/lib/api';
import { filterEntries, isFiltered, NO_FILTER, type Filter } from '@/lib/filter';
import { clock, countLabel, episodeCode, hueOf, shortTitle } from '@/lib/format';
import { continueLabel, groupWatched, ratioOf, resumeLabel } from '@/lib/progress';

import styles from './Library.module.css';
import { Sheet } from './Sheet';

interface Props {
  library: LibraryData | null;
  /** After a video was started: back to the remote. */
  onStarted: () => void;
  onError: (message: string) => void;
}

/** The library on the phone: what the TV shows follows along. */
export function Library({ library, onStarted, onError }: Props) {
  const [, params] = useRoute<{ id: string }>('/bibliotheque/g/:id');
  const [, navigate] = useLocation();
  const [picked, setPicked] = useState<Video | null>(null);
  const [filter, setFilter] = useState<Filter>(NO_FILTER);
  const groupId = params?.id ?? null;

  // The TV page follows: same page, the film picked here put forward there, the same search
  // (sent once typing pauses).
  useEffect(() => {
    const timer = setTimeout(() => {
      setView(groupId ? `/g/${groupId}` : '/', picked?.id ?? null, filter).catch(() => {});
    }, 200);
    return () => clearTimeout(timer);
  }, [groupId, picked, filter]);

  if (library === null) return <p className={styles.loading}>Les bobines arrivent…</p>;

  const start = (video: Video, from?: number) => {
    navigator.vibrate?.(8);
    setPicked(null);
    play(video.id, from)
      .then(onStarted)
      .catch(() => onError('Cette vidéo ne veut pas démarrer.'));
  };

  const group = groupId ? library.groups[groupId] : undefined;
  const filtered = isFiltered(filter);
  const entries = filtered ? filterEntries(library, filter) : library.entries;
  const kinds = [
    ['all', 'Tout'],
    ['films', 'Films'],
    ['series', 'Séries'],
  ] as const;

  return (
    <>
      {group ? (
        <section className={styles.page} aria-labelledby="group">
          <Link href="/bibliotheque" className={styles.back}>
            ‹ Bibliothèque
          </Link>
          <h1 id="group" className={styles.heading}>
            {group.title}
          </h1>
          <p className={styles.count}>{countLabel(group)}</p>
          <ol className={styles.rows}>
            {group.videos.map((id, index) => {
              const video = library.videos[id]!;
              return (
                <li key={id}>
                  <button type="button" className={styles.row} onClick={() => setPicked(video)}>
                    <Thumb video={video} />
                    <span className={styles.rowText}>
                      <span className={styles.rowKicker}>
                        {video.kind === 'episode' ? episodeCode(video) : `${index + 1}`}
                        {video.progress?.watched && ' · vu'}
                      </span>
                      <span className={styles.rowTitle}>{shortTitle(video)}</span>
                      {resumeLabel(video) && (
                        <span className={styles.rowResume}>{resumeLabel(video)}</span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </section>
      ) : (
        <section className={styles.page} aria-label="Bibliothèque">
          <h1 className={styles.heading}>Bibliothèque</h1>
          {library.entries.length === 0 && (
            <p className={styles.loading}>Rien à l’affiche… pour l’instant.</p>
          )}
          {library.entries.length > 0 && (
            <div className={styles.filters}>
              <input
                type="search"
                className={styles.search}
                placeholder="Chercher un film, une série…"
                aria-label="Chercher dans la bibliothèque"
                value={filter.query}
                onChange={(event) => setFilter({ ...filter, query: event.target.value })}
              />
              <div className={styles.chips} role="group" aria-label="Filtrer">
                {kinds.map(([kind, label]) => (
                  <button
                    key={kind}
                    type="button"
                    className={styles.chip}
                    aria-pressed={filter.kind === kind}
                    onClick={() => setFilter({ ...filter, kind })}
                  >
                    {label}
                  </button>
                ))}
                <button
                  type="button"
                  className={styles.chip}
                  aria-pressed={filter.unwatched}
                  onClick={() => setFilter({ ...filter, unwatched: !filter.unwatched })}
                >
                  Non vus
                </button>
              </div>
            </div>
          )}
          {filtered && entries.length === 0 && (
            <p className={styles.loading}>Rien ne correspond.</p>
          )}
          {!filtered && library.continue.length > 0 && (
            <>
              <h2 className={styles.subheading}>À suivre</h2>
              <div className={styles.shelf}>
                {library.continue.map((id) => {
                  const v = library.videos[id];
                  if (!v) return null;
                  const { title, detail } = continueLabel(library, v);
                  return (
                    <Card
                      key={id}
                      id={id}
                      title={title}
                      detail={detail}
                      image={v.thumb}
                      progress={ratioOf(v)}
                      onClick={() => setPicked(v)}
                    />
                  );
                })}
              </div>
              <h2 className={styles.subheading}>Tout</h2>
            </>
          )}
          <div className={styles.grid}>
            {entries.map(({ kind, id }) => {
              if (kind === 'group') {
                const g = library.groups[id]!;
                return (
                  <Card
                    key={id}
                    id={id}
                    title={g.title}
                    detail={countLabel(g)}
                    image={g.thumb}
                    watched={groupWatched(library, g)}
                    onClick={() => navigate(`/bibliotheque/g/${id}`)}
                  />
                );
              }
              const v = library.videos[id]!;
              return (
                <Card
                  key={id}
                  id={id}
                  title={v.title}
                  detail={v.year ? String(v.year) : ''}
                  image={v.thumb}
                  progress={ratioOf(v)}
                  watched={v.progress?.watched}
                  onClick={() => setPicked(v)}
                />
              );
            })}
          </div>
        </section>
      )}

      <Sheet
        title={picked ? (picked.kind === 'episode' ? shortTitle(picked) : picked.title) : ''}
        open={picked !== null}
        onClose={() => setPicked(null)}
      >
        {picked && <Picked video={picked} library={library} onStart={start} />}
      </Sheet>
    </>
  );
}

function Picked({
  video,
  library,
  onStart,
}: {
  video: Video;
  library: LibraryData;
  onStart: (video: Video, from?: number) => void;
}) {
  const resume = resumeLabel(video);
  const group = video.group ? library.groups[video.group] : undefined;
  const p = video.progress;
  return (
    <div className={styles.picked}>
      <Thumb video={video} large />
      <p className={styles.pickedInfo}>
        {[
          video.kind === 'episode' ? episodeCode(video) : null,
          video.kind === 'episode' ? video.title : null,
          video.year,
          p?.duration ? clock(p.duration) : null,
          p?.watched ? 'vu' : null,
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
      {resume ? (
        <>
          <button type="button" className={styles.primary} onClick={() => onStart(video)}>
            ▶ {resume}
          </button>
          <button type="button" className={styles.secondary} onClick={() => onStart(video, 0)}>
            Depuis le début
          </button>
        </>
      ) : (
        <button type="button" className={styles.primary} onClick={() => onStart(video, 0)}>
          ▶ Lecture
        </button>
      )}
      {group && group.videos.length > 1 && (
        <p className={styles.hint}>La suite s’enchaîne toute seule.</p>
      )}
    </div>
  );
}

function Card(props: {
  id: string;
  title: string;
  detail: string;
  image?: string | null;
  progress?: number;
  watched?: boolean;
  onClick: () => void;
}) {
  const style = { '--hue': hueOf(props.id) } as CSSProperties;
  return (
    <button type="button" className={styles.card} style={style} onClick={props.onClick}>
      {props.image && <img className={styles.cardImage} src={props.image} alt="" loading="lazy" />}
      {props.watched && (
        <span className={styles.watched} aria-label="Vu">
          ✓
        </span>
      )}
      <span className={styles.cardTitle}>{props.title}</span>
      {props.detail && <span className={styles.cardDetail}>{props.detail}</span>}
      {!!props.progress && (
        <span className={styles.bar} aria-hidden="true">
          <span style={{ width: `${props.progress * 100}%` }} />
        </span>
      )}
    </button>
  );
}

function Thumb({ video, large = false }: { video: Video; large?: boolean }) {
  const ratio = ratioOf(video);
  return (
    <span
      className={large ? styles.thumbLarge : styles.thumb}
      style={{ '--hue': hueOf(video.id) } as CSSProperties}
      aria-hidden="true"
    >
      {video.thumb && <img src={video.thumb} alt="" loading="lazy" />}
      {ratio > 0 && (
        <span className={styles.bar}>
          <span style={{ width: `${ratio * 100}%` }} />
        </span>
      )}
    </span>
  );
}
