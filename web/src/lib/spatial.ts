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
 * The index of the best candidate in `direction` from `from`, or -1. A candidate must lie that
 * way; among them, the one closest along the direction wins, with the sideways offset weighing
 * more (so that "down" goes to the card below rather than to a nearer one diagonally).
 */
export function nearest(from: Box, candidates: Box[], direction: Direction): number {
  const a = center(from);
  let best = -1;
  let bestScore = Infinity;
  candidates.forEach((box, index) => {
    const b = center(box);
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const along =
      direction === 'left' ? -dx : direction === 'right' ? dx : direction === 'up' ? -dy : dy;
    const across = direction === 'left' || direction === 'right' ? Math.abs(dy) : Math.abs(dx);
    if (along <= 1) return; // not in that direction (or the element itself)
    const score = along + across * 3;
    if (score < bestScore) {
      bestScore = score;
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

/** Moves the focus among the elements marked `data-nav` inside `root`. */
export function moveFocus(root: ParentNode, direction: Direction): boolean {
  const items = [...root.querySelectorAll<HTMLElement>('[data-nav]')];
  if (items.length === 0) return false;
  const current = document.activeElement as HTMLElement | null;
  if (!current || !items.includes(current)) {
    items[0]?.focus();
    return true;
  }
  const index = nearest(
    current.getBoundingClientRect(),
    items.map((el) => el.getBoundingClientRect()),
    direction,
  );
  if (index === -1) return false;
  const target = items[index];
  target?.focus();
  target?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
  return true;
}
