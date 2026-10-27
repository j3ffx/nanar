import { useEffect, useState } from 'react';

/** True once nobody has touched the keyboard or the mouse for `ms`; any input wakes it. */
export function useIdle(ms: number): boolean {
  const [idle, setIdle] = useState(false);
  useEffect(() => {
    let timer = setTimeout(() => setIdle(true), ms);
    const wake = () => {
      clearTimeout(timer);
      setIdle(false);
      timer = setTimeout(() => setIdle(true), ms);
    };
    const events = ['keydown', 'pointermove', 'pointerdown', 'wheel'] as const;
    events.forEach((name) => window.addEventListener(name, wake, { passive: true }));
    return () => {
      clearTimeout(timer);
      events.forEach((name) => window.removeEventListener(name, wake));
    };
  }, [ms]);
  return idle;
}
