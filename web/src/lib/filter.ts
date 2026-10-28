import type { Library } from './api';
import { groupWatched } from './progress';

/** What the library shows: searched on the phone, followed by the TV (`State.view.filter`). */
export interface Filter {
  query: string;
  kind: 'all' | 'films' | 'series';
  unwatched: boolean;
}

export const NO_FILTER: Filter = { query: '', kind: 'all', unwatched: false };

export function isFiltered(filter: Filter): boolean {
  return filter.query.trim() !== '' || filter.kind !== 'all' || filter.unwatched;
}

/** Lower case, without accents: "Karaté" is found by "karate". */
export function fold(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}

/**
 * The top-level entries the filter keeps. Every word searched must appear somewhere: a saga or a
 * series stays when its title or one of its videos matches. Sagas count as films.
 */
export function filterEntries(library: Library, filter: Filter): Library['entries'] {
  const words = fold(filter.query)
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean);
  const matches = (texts: (string | number | null)[]) => {
    const haystack = fold(texts.filter((t) => t !== null).join(' '));
    return words.every((word) => haystack.includes(word));
  };
  return library.entries.filter(({ kind, id }) => {
    if (kind === 'group') {
      const group = library.groups[id];
      if (!group) return false;
      const series = group.kind === 'series';
      if ((filter.kind === 'films' && series) || (filter.kind === 'series' && !series))
        return false;
      if (filter.unwatched && groupWatched(library, group)) return false;
      const videos = group.videos.map((v) => library.videos[v]).filter((v) => v !== undefined);
      return matches([group.title, ...videos.flatMap((v) => [v.title, v.episodeTitle])]);
    }
    const video = library.videos[id];
    if (!video || filter.kind === 'series') return false;
    if (filter.unwatched && video.progress?.watched) return false;
    return matches([video.title, video.year]);
  });
}

/** « requin » · films · non vus */
export function filterLabel(filter: Filter): string {
  const parts = [
    filter.query.trim() ? `« ${filter.query.trim()} »` : null,
    filter.kind === 'films' ? 'films' : filter.kind === 'series' ? 'séries' : null,
    filter.unwatched ? 'non vus' : null,
  ];
  return parts.filter(Boolean).join(' · ');
}
