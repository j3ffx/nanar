import { describe, expect, it } from 'vitest';

import type { Library, Video } from './api';
import { filterEntries, filterLabel, fold, isFiltered, NO_FILTER } from './filter';

const video = (id: string, title: string, extra: Partial<Video> = {}): Video => ({
  id,
  title,
  kind: 'movie',
  year: null,
  season: null,
  episode: null,
  episodeTitle: null,
  group: null,
  ...extra,
});

const watched = { position: 0, duration: 100, watched: true };

const library: Library = {
  root: '/films',
  videos: {
    k: video('k', 'Karaté Cowboy', { year: 1984, progress: watched }),
    z: video('z', 'Zombies au ski', { year: 2003 }),
    r1: video('r1', 'Le Requin Volant', { group: 'saga' }),
    r2: video('r2', 'Le Requin Volant 2 - La Revanche', { group: 'saga' }),
    e1: video('e1', 'Les Brigades', {
      kind: 'episode',
      group: 'series',
      episodeTitle: 'Fausse piste',
      progress: watched,
    }),
  },
  groups: {
    saga: { id: 'saga', kind: 'saga', title: 'La Trilogie du Requin', videos: ['r1', 'r2'] },
    series: { id: 'series', kind: 'series', title: 'Les Brigades', videos: ['e1'] },
  },
  entries: [
    { kind: 'video', id: 'k' },
    { kind: 'group', id: 'series' },
    { kind: 'group', id: 'saga' },
    { kind: 'video', id: 'z' },
  ],
  continue: [],
};

const ids = (filter: Partial<typeof NO_FILTER>) =>
  filterEntries(library, { ...NO_FILTER, ...filter }).map((e) => e.id);

describe('filter', () => {
  it('keeps everything when nothing is asked', () => {
    expect(ids({})).toEqual(['k', 'series', 'saga', 'z']);
    expect(isFiltered(NO_FILTER)).toBe(false);
  });

  it('finds titles whatever the accents and capitals', () => {
    expect(fold('Karaté')).toBe('karate');
    expect(ids({ query: 'KARATE' })).toEqual(['k']);
    expect(ids({ query: '1984' })).toEqual(['k']);
  });

  it('finds a saga or a series by one of its videos, every word somewhere', () => {
    expect(ids({ query: 'revanche' })).toEqual(['saga']);
    expect(ids({ query: 'requin revanche' })).toEqual(['saga']);
    expect(ids({ query: 'fausse piste' })).toEqual(['series']);
    expect(ids({ query: 'requin ski' })).toEqual([]);
  });

  it('separates films (sagas included) from series', () => {
    expect(ids({ kind: 'films' })).toEqual(['k', 'saga', 'z']);
    expect(ids({ kind: 'series' })).toEqual(['series']);
  });

  it('leaves out what was watched', () => {
    expect(ids({ unwatched: true })).toEqual(['saga', 'z']);
  });

  it('says what is shown', () => {
    expect(filterLabel({ query: ' requin ', kind: 'films', unwatched: true })).toBe(
      '« requin » · films · non vus',
    );
  });
});
