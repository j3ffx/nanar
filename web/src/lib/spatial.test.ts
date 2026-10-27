import { describe, expect, it } from 'vitest';

import { nearest, type Box } from './spatial';

// A grid of 3 columns and 2 rows of 100×150 cards, 20 px apart.
const card = (col: number, row: number): Box => ({
  left: col * 120,
  top: row * 170,
  width: 100,
  height: 150,
});
const grid = [card(0, 0), card(1, 0), card(2, 0), card(0, 1), card(1, 1)];

describe('nearest', () => {
  it('moves along a row', () => {
    expect(nearest(card(0, 0), grid, 'right')).toBe(1);
    expect(nearest(card(1, 0), grid, 'left')).toBe(0);
  });

  it('goes straight down rather than diagonally', () => {
    expect(nearest(card(1, 0), grid, 'down')).toBe(4);
  });

  it('finds the closest card below when the row below is shorter', () => {
    expect(nearest(card(2, 0), grid, 'down')).toBe(4);
  });

  it('returns -1 at an edge', () => {
    expect(nearest(card(0, 0), grid, 'left')).toBe(-1);
    expect(nearest(card(0, 0), grid, 'up')).toBe(-1);
  });
});
