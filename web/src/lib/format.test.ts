import { describe, expect, it } from 'vitest';

import type { Video } from './api';
import { clock, countLabel, episodeCode, hueOf, shortTitle } from './format';

const episode: Video = {
  id: 'a1',
  title: 'Les Brigades du Nanar',
  kind: 'episode',
  year: null,
  season: 1,
  episode: 3,
  episodeTitle: null,
  group: 'g',
};

describe('format', () => {
  it('writes a duration like a player does', () => {
    expect(clock(65)).toBe('1:05');
    expect(clock(3723)).toBe('1:02:03');
    expect(clock(-4)).toBe('0:00');
  });

  it('names episodes', () => {
    expect(episodeCode(episode)).toBe('S01E03');
    expect(shortTitle(episode)).toBe('S01E03');
    expect(shortTitle({ ...episode, episodeTitle: 'Le Retour' })).toBe('Le Retour');
  });

  it('counts the videos of a group', () => {
    expect(countLabel({ id: 'g', kind: 'saga', title: 'T', videos: ['a', 'b'] })).toBe('2 films');
    expect(countLabel({ id: 'g', kind: 'series', title: 'T', videos: ['a'] })).toBe('1 épisode');
  });

  it('keeps a stable hue per id', () => {
    expect(hueOf('abc')).toBe(hueOf('abc'));
    expect(hueOf('abc')).toBeGreaterThanOrEqual(0);
    expect(hueOf('abc')).toBeLessThan(360);
  });
});
