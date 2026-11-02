// Arrow-key navigation on the TV: from the focused element, the nearest one in that direction.

export type Direction = 'up' | 'down' | 'left' | 'right';

export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

const center = (b: Box) => ({ x: b.left + b.width / 2, y: b.top + b.height / 2 });

/**
 * The index of the best candidate in `direction` from `from`, or -1.
 *
 * Up and down go to the very next row, whatever its length, then to its closest card: a section
 * is never skipped. Left and right stay on the same row, and stop at its end.
 */
export function nearest(from: Box, candidates: Box[], direction: Direction): number {
  const a = center(from);
  const vertical = direction === 'up' || direction === 'down';
  const sign = direction === 'up' || direction === 'left' ? -1 : 1;
  let best = -1;
  let bestScore = Infinity;
  if (!vertical) {
    candidates.forEach((box, index) => {
      const b = center(box);
      const along = sign * (b.x - a.x);
      const sameRow = box.top < from.top + from.height && box.top + box.height > from.top;
      if (along > 1 && sameRow && along < bestScore) {
        bestScore = along;
        best = index;
      }
    });
    return best;
  }
  const away = candidates.map((box) => sign * (center(box).y - a.y));
  const closest = Math.min(...away.filter((distance) => distance > 1));
  if (closest === Infinity) return -1;
  const row = candidates[away.indexOf(closest)]!;
  candidates.forEach((box, index) => {
    const inRow = box.top < row.top + row.height && box.top + box.height > row.top;
    const across = Math.abs(center(box).x - a.x);
    if (away[index]! > 1 && inRow && across < bestScore) {
      bestScore = across;
      best = index;
    }
  });
  return best;
}

export const DIRECTIONS: Record<string, Direction> = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
};

/** Smooth, unless the user asked for less motion: an explicit `smooth` overrides the CSS. */
export function scrollBehavior(): ScrollBehavior {
  return matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
}

/** Moves the focus among the elements marked `data-nav` inside `root`. */
export function moveFocus(root: ParentNode, direction: Direction): boolean {
  const items = [...root.querySelectorAll<HTMLElement>('[data-nav]:not(:disabled)')];
  if (items.length === 0) return false;
  const current = document.activeElement as HTMLElement | null;
  if (!current || !items.includes(current)) {
    items[0]?.focus();
    return true;
  }
  // The page and the header above it are apart: rows scrolled out of sight lie behind the header,
  // and are nearer to it than the row on screen.
  const among = (list: HTMLElement[]) =>
    list[
      nearest(
        current.getBoundingClientRect(),
        list.map((el) => el.getBoundingClientRect()),
        direction,
      )
    ];
  const page = items.filter((el) => el.closest('main'));
  const header = items.filter((el) => !el.closest('main'));
  let target: HTMLElement | undefined;
  if (current.closest('main')) {
    target = among(page) ?? (direction === 'up' ? among(header) : undefined);
  } else if (direction === 'down') {
    const main = root.querySelector('main')?.getBoundingClientRect().top ?? 0;
    target = among(page.filter((el) => el.getBoundingClientRect().bottom > main));
  } else {
    target = among(header);
  }
  if (!target) return false;
  target?.focus();
  target?.scrollIntoView({ block: 'center', inline: 'nearest', behavior: scrollBehavior() });
  return true;
}
