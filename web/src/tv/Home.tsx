import { useLocation } from 'wouter';

import { play, type Library } from '@/lib/api';
import { countLabel } from '@/lib/format';
import { groupWatched, ratioOf } from '@/lib/progress';

import { Poster } from './Poster';
import styles from './Tv.module.css';

interface Props {
  library: Library;
  onError: (message: string) => void;
}

/** The whole library: sagas and series first, then the films on their own. */
export function Home({ library, onError }: Props) {
  const [, navigate] = useLocation();
  const groups = library.entries.filter((e) => e.kind === 'group');
  const films = library.entries.filter((e) => e.kind === 'video');

  if (library.entries.length === 0) {
    return (
      <div className={styles.empty}>
        <p className={styles.emptyTitle}>Rien à l’affiche… pour l’instant.</p>
        <p>Aucune vidéo dans {library.root}.</p>
      </div>
    );
  }

  const start = (id: string) => play(id).catch(() => onError('Cette vidéo ne veut pas démarrer.'));

  return (
    <>
      {groups.length > 0 && (
        <section aria-labelledby="sagas">
          <h2 id="sagas" className={styles.section}>
            Sagas et séries
          </h2>
          <div className={styles.grid}>
            {groups.map(({ id }) => {
              const group = library.groups[id]!;
              return (
                <Poster
                  key={id}
                  id={id}
                  title={group.title}
                  detail={countLabel(group)}
                  image={group.thumb}
                  watched={groupWatched(library, group)}
                  stacked
                  onActivate={() => navigate(`/g/${id}`)}
                />
              );
            })}
          </div>
        </section>
      )}
      {films.length > 0 && (
        <section aria-labelledby="films">
          <h2 id="films" className={styles.section}>
            Films
          </h2>
          <div className={styles.grid}>
            {films.map(({ id }) => {
              const video = library.videos[id]!;
              return (
                <Poster
                  key={id}
                  id={id}
                  title={video.title}
                  detail={video.year ?? ''}
                  image={video.thumb}
                  progress={ratioOf(video)}
                  watched={video.progress?.watched}
                  onActivate={() => void start(id)}
                />
              );
            })}
          </div>
        </section>
      )}
    </>
  );
}
