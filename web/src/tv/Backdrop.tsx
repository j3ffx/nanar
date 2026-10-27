import styles from './Backdrop.module.css';

/** The moving background: a projector's beam sweeping slowly over coloured haze, and grain. */
export function Backdrop() {
  return (
    <div className={styles.backdrop} aria-hidden="true">
      <div className={`${styles.blob} ${styles.plum}`} />
      <div className={`${styles.blob} ${styles.popcorn}`} />
      <div className={`${styles.blob} ${styles.cherry}`} />
      <div className={styles.beam} />
      <div className={styles.grain} />
    </div>
  );
}
