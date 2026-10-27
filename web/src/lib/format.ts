import type { Group, Video } from './api';

/** A hue (0–359) derived from an id, so that each poster keeps its colour. */
export function hueOf(id: string): number {
  let hash = 0;
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return hash % 360;
}

/** "1:02:03", or "4:05" under an hour. */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${rest}` : `${m}:${rest}`;
}

/** "S01E03", for an episode. */
export function episodeCode(video: Video): string {
  const pad = (n: number | null) => String(n ?? 0).padStart(2, '0');
  return `S${pad(video.season)}E${pad(video.episode)}`;
}

/** What a video is called inside its group: the episode's own title, or the film's. */
export function shortTitle(video: Video): string {
  if (video.kind === 'episode') return video.episodeTitle ?? episodeCode(video);
  return video.title;
}

/** "8 films", "4 épisodes". */
export function countLabel(group: Group): string {
  const n = group.videos.length;
  if (group.kind === 'series') return n > 1 ? `${n} épisodes` : '1 épisode';
  return n > 1 ? `${n} films` : '1 film';
}
