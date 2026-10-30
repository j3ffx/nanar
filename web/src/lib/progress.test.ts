import { describe, expect, it } from 'vitest';

import type { Group, Library, Video } from './api';
import { continueLabel, groupNext, groupWatched, ratioOf, resumeLabel } from './progress';

const video = (id: string, progress: Video['progress']): Video => ({
  id,
  title: id,
  kind: 'episode',
  year: null,
  season: 1,
  episode: Number(id.slice(1)),
  episodeTitle: null,
  group: 'g',
  progress,
});

const library = (videos: Video[]): Library => ({
  root: '/films',
  videos: Object.fromEntries(videos.map((v) => [v.id, v])),
  groups: { g: group },
  entries: [],
  continue: [],
  recent: [],
});

const group: Group = { id: 'g', kind: 'series', title: 'S', videos: ['e1', 'e2', 'e3'] };

describe('progress', () => {
  it('measures how far a video went', () => {
    expect(ratioOf(video('e1', { position: 300, duration: 1200, watched: false }))).toBe(0.25);
    expect(ratioOf(video('e1', null))).toBe(0);
  });

  it('offers to resume past the first minute only', () => {
    expect(resumeLabel(video('e1', { position: 2530, duration: 6000, watched: false }))).toBe(
      'Reprendre à 42:10',
    );
    expect(resumeLabel(video('e1', { position: 30, duration: 6000, watched: false }))).toBeNull();
  });

  it('picks the episode to watch next', () => {
    const watched = { position: 0, duration: 1200, watched: true };
    const lib = library([
      video('e1', watched),
      video('e2', { position: 400, duration: 1200, watched: false }),
      video('e3', null),
    ]);
    expect(groupNext(lib, group)?.id).toBe('e2');
    const fresh = library([video('e1', watched), video('e2', null), video('e3', null)]);
    expect(groupNext(fresh, group)?.id).toBe('e2');
    expect(groupWatched(fresh, group)).toBe(false);
    const done = library([video('e1', watched), video('e2', watched), video('e3', watched)]);
    expect(groupWatched(done, group)).toBe(true);
    expect(groupNext(done, group)?.id).toBe('e1');
  });

  it('names what to continue by its series, then where it stands', () => {
    const lib = library([
      video('e1', { position: 0, duration: 1200, watched: true }),
      video('e2', { position: 600, duration: 1200, watched: false }),
      video('e3', null),
    ]);
    expect(continueLabel(lib, lib.videos.e2!)).toEqual({
      title: 'S',
      detail: 'S01E02 · Reprendre à 10:00',
    });
    expect(continueLabel(lib, lib.videos.e3!)).toEqual({
      title: 'S',
      detail: 'S01E03 · Épisode suivant',
    });
  });
});
