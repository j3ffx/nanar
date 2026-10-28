import type { Group, Library, Video } from './api';
import { clock, episodeCode } from './format';

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

/** How a video of "À suivre" is named: its series or film, then where it stands. */
export function continueLabel(library: Library, video: Video): { title: string; detail: string } {
  const group = video.group ? library.groups[video.group] : undefined;
  const title = video.kind === 'episode' && group ? group.title : video.title;
  const where = video.kind === 'episode' ? episodeCode(video) : null;
  const resume = resumeLabel(video);
  const detail = [where, resume ?? (where ? 'Épisode suivant' : 'Film suivant')];
  return { title, detail: detail.filter(Boolean).join(' · ') };
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
