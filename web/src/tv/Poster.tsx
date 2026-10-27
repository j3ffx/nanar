import type { CSSProperties, ReactNode } from 'react';

import { hueOf } from '@/lib/format';

import styles from './Poster.module.css';

interface Props {
  id: string;
  title: string;
  detail: ReactNode;
  /** The video's picture (a poster or a frame); a colour of its own stands in without one. */
  image?: string | null;
  /** How far it was watched, 0 to 1 (a bar along the bottom). */
  progress?: number;
  watched?: boolean;
  stacked?: boolean;
  onActivate: () => void;
}

export function Poster({
  id,
  title,
  detail,
  image,
  progress,
  watched = false,
  stacked = false,
  onActivate,
}: Props) {
  const style = { '--hue': hueOf(id) } as CSSProperties;
  return (
    <button
      type="button"
      className={styles.poster}
      data-nav
      data-id={id}
      data-stacked={stacked || undefined}
      data-image={image ? true : undefined}
      style={style}
      onClick={onActivate}
    >
      <span className={styles.face}>
        {image && <img className={styles.image} src={image} alt="" loading="lazy" />}
        {watched && (
          <span className={styles.watched} aria-label="Vu">
            ✓
          </span>
        )}
        <span className={styles.title}>{title}</span>
        <span className={styles.detail}>{detail}</span>
        {progress !== undefined && progress > 0 && (
          <span className={styles.progress} aria-hidden="true">
            <span style={{ width: `${Math.min(100, progress * 100)}%` }} />
          </span>
        )}
      </span>
    </button>
  );
}
