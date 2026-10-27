import { useLocation } from 'wouter';

import { answerIntegration, chooseFolder, play, type Library } from '@/lib/api';
import { countLabel } from '@/lib/format';
import { groupWatched, ratioOf } from '@/lib/progress';

import { Poster } from './Poster';
import styles from './Tv.module.css';

interface Props {
  library: Library;
  /** The Windows build's first run: offer the Start menu and the right-click menu. */
  offerIntegration: boolean;
  onError: (message: string) => void;
}

/** The whole library: sagas and series first, then the films on their own. */
export function Home({ library, offerIntegration, onError }: Props) {
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
      <p className={styles.folder}>
        {library.root}
        <button type="button" data-nav onClick={() => void choose()}>
          Changer de dossier
        </button>
      </p>
    </>
  );
}
