import type { CSSProperties, ReactNode } from 'react';

import { hueOf } from '@/lib/format';

import styles from './Poster.module.css';

interface Props {
  id: string;
  title: string;
  detail: ReactNode;
  stacked?: boolean;
  onActivate: () => void;
}

/**
 * A card standing in for a poster: the title on a colour of its own. Real thumbnails replace
 * the colour later; the card stays the same.
 */
export function Poster({ id, title, detail, stacked = false, onActivate }: Props) {
  const style = { '--hue': hueOf(id) } as CSSProperties;
  return (
    <button
      type="button"
      className={styles.poster}
      data-nav
      data-id={id}
      data-stacked={stacked || undefined}
      style={style}
      onClick={onActivate}
    >
      <span className={styles.face}>
        <span className={styles.title}>{title}</span>
        <span className={styles.detail}>{detail}</span>
      </span>
    </button>
  );
}
