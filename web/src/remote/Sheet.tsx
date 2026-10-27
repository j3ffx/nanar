import { useEffect, useRef, type ReactNode } from 'react';

import styles from './Remote.module.css';

interface Props {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

/** A panel rising from the bottom of the screen, over the remote (a modal <dialog>). */
export function Sheet({ title, open, onClose, children }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  return (
    <dialog
      ref={dialog}
      className={styles.sheet}
      aria-label={title}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === dialog.current) onClose(); // a tap on the backdrop
      }}
    >
      <div className={styles.sheetBody}>
        <div className={styles.sheetHeader}>
          <h2 className={styles.sheetTitle}>{title}</h2>
          <button type="button" className={styles.sheetClose} onClick={onClose}>
            OK
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
