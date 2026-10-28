import { useLocation } from 'wouter';

import { answerIntegration, chooseFolder, play, type Library } from '@/lib/api';
import { filterEntries, filterLabel, isFiltered, type Filter } from '@/lib/filter';
import { countLabel } from '@/lib/format';
import { continueLabel, groupWatched, ratioOf } from '@/lib/progress';

import { Poster } from './Poster';
import styles from './Tv.module.css';

interface Props {
  library: Library;
  /** What a phone searches: the TV shows the same results. */
  filter: Filter;
  /** The Windows build's first run: offer the Start menu and the right-click menu. */
  offerIntegration: boolean;
  onError: (message: string) => void;
}

/** The whole library: what to continue, sagas and series, then the films on their own. */
export function Home({ library, filter, offerIntegration, onError }: Props) {
  const [, navigate] = useLocation();
  const groups = library.entries.filter((e) => e.kind === 'group');
  const films = library.entries.filter((e) => e.kind === 'video');

  const choose = () => chooseFolder().catch(() => onError('Ce dossier ne s’ouvre pas.'));

  if (library.root === '') {
    return (
      <div className={styles.empty}>
        <p className={styles.emptyTitle}>Bienvenue dans ta salle de projection.</p>
        <p>Montre à Nanar où sont tes films et tes séries.</p>
        <button type="button" data-nav className={styles.back} onClick={() => void choose()}>
          Choisir mon dossier de films
        </button>
      </div>
    );
  }

  if (library.entries.length === 0) {
    return (
      <div className={styles.empty}>
        <p className={styles.emptyTitle}>Rien à l’affiche… pour l’instant.</p>
        <p>Aucune vidéo dans {library.root}.</p>
        <button type="button" data-nav className={styles.back} onClick={() => void choose()}>
          Choisir un autre dossier
        </button>
      </div>
    );
  }

  const start = (id: string) => play(id).catch(() => onError('Cette vidéo ne veut pas démarrer.'));

  const groupPoster = (id: string) => {
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
  };

  const filmPoster = (id: string) => {
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
  };

  if (isFiltered(filter)) {
    const found = filterEntries(library, filter);
    return (
      <section aria-labelledby="results">
        <h2 id="results" className={styles.section}>
          Recherche : {filterLabel(filter)}
        </h2>
        {found.length === 0 ? (
          <p className={styles.nothing}>Rien ne correspond.</p>
        ) : (
          <div className={styles.grid}>
            {found.map(({ kind, id }) => (kind === 'group' ? groupPoster(id) : filmPoster(id)))}
          </div>
        )}
      </section>
    );
  }

  return (
    <>
      {offerIntegration && (
        <aside className={styles.offer}>
          <p>
            Ajouter Nanar au menu Démarrer, et « Ouvrir avec Nanar » au clic droit sur les dossiers
            ?
          </p>
          <button type="button" data-nav onClick={() => void answerIntegration(true)}>
            Oui
          </button>
          <button type="button" data-nav onClick={() => void answerIntegration(false)}>
            Non merci
          </button>
        </aside>
      )}
      {library.continue.length > 0 && (
        <section aria-labelledby="continue">
          <h2 id="continue" className={styles.section}>
            À suivre
          </h2>
          <div className={styles.grid}>
            {library.continue.map((id) => {
              const video = library.videos[id];
              if (!video) return null;
              const { title, detail } = continueLabel(library, video);
              return (
                <Poster
                  key={id}
                  id={id}
                  title={title}
                  detail={detail}
                  image={video.thumb}
                  progress={ratioOf(video)}
                  onActivate={() => void start(id)}
                />
              );
            })}
          </div>
        </section>
      )}
      {groups.length > 0 && (
        <section aria-labelledby="sagas">
          <h2 id="sagas" className={styles.section}>
            Sagas et séries
          </h2>
          <div className={styles.grid}>{groups.map(({ id }) => groupPoster(id))}</div>
        </section>
      )}
      {films.length > 0 && (
        <section aria-labelledby="films">
          <h2 id="films" className={styles.section}>
            Films
          </h2>
          <div className={styles.grid}>{films.map(({ id }) => filmPoster(id))}</div>
        </section>
      )}
      <p className={styles.folder}>
        {library.root}
        <button type="button" data-nav onClick={() => void choose()}>
          Changer de dossier
        </button>
      </p>
    </>
  );
}
