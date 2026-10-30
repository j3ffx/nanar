import styles from './Tv.module.css';

/** Up one level, as `Échap` does: for the mouse, and reachable with the arrows (up from the top). */
export function BackButton({ onBack }: { onBack: () => void }) {
  return (
    <button type="button" data-nav data-back className={styles.backButton} onClick={onBack}>
      <span aria-hidden="true">←</span> Retour
    </button>
  );
}
