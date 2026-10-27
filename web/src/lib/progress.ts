import type { Group, Library, Video } from './api';
import { clock } from './format';

/** How far a video was watched, 0 to 1 (0 when never started or watched to its end). */
export function ratioOf(video: Video): number {
  const p = video.progress;
  if (!p || !p.duration || p.position <= 0) return 0;
  return Math.min(1, p.position / p.duration);
}

/** "Reprendre à 42:10" when a video was left in the middle, else null. */
export function resumeLabel(video: Video): string | null {
  const p = video.progress;
  if (!p || p.position < 60) return null; // under a minute, Nanar starts over (progress.py)
  return `Reprendre à ${clock(p.position)}`;
}

/** Whether every video of a group was watched. */
export function groupWatched(library: Library, group: Group): boolean {
  return group.videos.every((id) => library.videos[id]?.progress?.watched);
}

/** The video of a group to play next: the first one left in the middle, else the first not
 *  watched, else the first. */
export function groupNext(library: Library, group: Group): Video | undefined {
  const videos = group.videos.map((id) => library.videos[id]).filter((v): v is Video => !!v);
  return (
    videos.find((v) => resumeLabel(v)) ?? videos.find((v) => !v.progress?.watched) ?? videos[0]
  );
}
