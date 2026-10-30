import type { CSSProperties } from 'react';
import { Link } from 'wouter';

import { play, type Library } from '@/lib/api';
import { countLabel, episodeCode, hueOf, shortTitle } from '@/lib/format';
import { ratioOf, resumeLabel } from '@/lib/progress';

import { BackButton } from './BackButton';
import styles from './Tv.module.css';

interface Props {
  library: Library;
  groupId: string;
  onBack: () => void;
  onError: (message: string) => void;
}

/** A saga or a series, in order: one line per film or episode. */
export function GroupPage({ library, groupId, onBack, onError }: Props) {
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
      <BackButton onBack={onBack} />
      <h2 id="group-title" className={styles.groupTitle}>
        {group.title}
        <span className={styles.groupCount}>{countLabel(group)}</span>
      </h2>
      <ol className={styles.list}>
        {group.videos.map((id, index) => {
          const video = library.videos[id]!;
          const ratio = ratioOf(video);
          const resume = resumeLabel(video);
          return (
            <li key={id}>
              <button
                type="button"
                data-nav
                data-id={id}
                className={styles.row}
                onClick={() => void start(id)}
              >
                <span
                  className={styles.rowThumb}
                  style={{ '--hue': hueOf(id) } as CSSProperties}
                  aria-hidden="true"
                >
                  {video.thumb && <img src={video.thumb} alt="" loading="lazy" />}
                  {ratio > 0 && (
                    <span className={styles.rowProgress}>
                      <span style={{ width: `${ratio * 100}%` }} />
                    </span>
                  )}
                </span>
                <span className={styles.rowNumber}>
                  {video.kind === 'episode' ? episodeCode(video) : index + 1}
                </span>
                <span className={styles.rowText}>
                  <span className={styles.rowTitle}>{shortTitle(video)}</span>
                  {resume && <span className={styles.rowResume}>{resume}</span>}
                </span>
                <span className={styles.rowDetail}>
                  {video.progress?.watched && (
                    <span className={styles.rowWatched} aria-label="Vu">
                      ✓
                    </span>
                  )}
                  {video.year}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
