import { useEffect, useState } from 'react';

/** True once nobody has touched the keyboard or the mouse for `ms`, and `activity` hasn't
 *  changed either; any of them wakes it. */
export function useIdle(ms: number, activity: string): boolean {
  const [idleSince, setIdleSince] = useState<string | null>(null); // the activity it outlasted
  useEffect(() => {
    let timer = setTimeout(() => setIdleSince(activity), ms);
    const wake = () => {
      clearTimeout(timer);
      setIdleSince(null);
      timer = setTimeout(() => setIdleSince(activity), ms);
    };
    const events = ['keydown', 'pointermove', 'pointerdown', 'wheel'] as const;
    events.forEach((name) => window.addEventListener(name, wake, { passive: true }));
    return () => {
      clearTimeout(timer);
      events.forEach((name) => window.removeEventListener(name, wake));
    };
  }, [ms, activity]);
  return idleSince === activity;
}
