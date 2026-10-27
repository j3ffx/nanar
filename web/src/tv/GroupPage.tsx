import { Link } from 'wouter';

import { play, type Library } from '@/lib/api';
import { countLabel, episodeCode, shortTitle } from '@/lib/format';

import styles from './Tv.module.css';

interface Props {
  library: Library;
  groupId: string;
  onError: (message: string) => void;
}

/** A saga or a series, in order: one line per film or episode. */
export function GroupPage({ library, groupId, onError }: Props) {
  const group = library.groups[groupId];
  if (!group) {
    return (
      <div className={styles.empty}>
        <p className={styles.emptyTitle}>Cette bobine s’est perdue.</p>
        <Link href="/" data-nav className={styles.back}>
          Retour à la bibliothèque
        </Link>
      </div>
    );
  }
  const start = (id: string) => play(id).catch(() => onError('Cette vidéo ne veut pas démarrer.'));

  return (
    <section aria-labelledby="group-title">
      <h2 id="group-title" className={styles.groupTitle}>
        {group.title}
        <span className={styles.groupCount}>{countLabel(group)}</span>
      </h2>
      <ol className={styles.list}>
        {group.videos.map((id, index) => {
          const video = library.videos[id]!;
          return (
            <li key={id}>
              <button type="button" data-nav className={styles.row} onClick={() => void start(id)}>
                <span className={styles.rowNumber}>
                  {video.kind === 'episode' ? episodeCode(video) : index + 1}
                </span>
                <span className={styles.rowTitle}>{shortTitle(video)}</span>
                {video.year && <span className={styles.rowDetail}>{video.year}</span>}
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
