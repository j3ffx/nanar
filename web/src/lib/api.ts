import { useEffect, useState } from 'react';

import type { Filter } from './filter';

// The shapes the Python API sends (src/nanar/library.py, src/nanar/controller.py).

export interface Video {
  id: string;
  title: string;
  kind: 'movie' | 'episode';
  year: number | null;
  season: number | null;
  episode: number | null;
  episodeTitle: string | null;
  group: string | null;
  /** Where it was left, and its picture (given with the library, not in the live state). */
  progress?: Progress | null;
  thumb?: string | null;
  /** TMDb's summary, when the user gave Nanar a key (films only). */
  overview?: string | null;
}

export interface Progress {
  position: number;
  duration: number | null;
  watched: boolean;
}

export interface UpNext {
  video: Video;
  seconds: number;
}

export interface Group {
  id: string;
  kind: 'saga' | 'series';
  title: string;
  videos: string[];
  thumb?: string | null;
  /** TMDb's summary of a series, when the user gave Nanar a key. */
  overview?: string | null;
}

export interface Library {
  root: string;
  videos: Record<string, Video>;
  groups: Record<string, Group>;
  entries: { kind: 'video' | 'group'; id: string }[];
  /** "À suivre": videos left in the middle, and the next of a saga or a series. */
  continue: string[];
  /** "Récemment ajoutés": entries with a video new in the folder, the newest first. */
  recent: { kind: 'video' | 'group'; id: string }[];
}

export interface Track {
  id: number;
  label: string;
  lang: string | null;
  title: string | null;
  selected: boolean;
  external: boolean;
}

export interface Playing {
  video: Video;
  position: number;
  duration: number | null;
  paused: boolean;
  volume: number;
  muted: boolean;
  subDelay: number;
  subScale: number;
  /** The chapter shown (from 0), and how many the video has (0: none). */
  chapter: number | null;
  chapters: number;
  audio: Track[];
  subs: Track[];
  hasNext: boolean;
  hasPrevious: boolean;
}

export interface State {
  folder: string;
  demo: boolean;
  fullscreen: boolean;
  phones: number;
  libraryVersion: number;
  playing: Playing | null;
  upNext: UpNext | null;
  /** Night mode: loud scenes softer, for the rest of the evening. */
  night: boolean;
  /** Stops at the end of this video, or in `remaining` seconds. */
  sleep: { kind: 'end' } | { kind: 'timer'; remaining: number } | null;
  /** Mode hôtel: the PC's own Wi-Fi, which phones join to reach Nanar. */
  hotspot: { available: boolean; on: boolean; ssid: string | null };
  /** New versions of the Windows build, looked for on GitHub when the user said so. */
  updates: {
    supported: boolean;
    enabled: boolean;
    available: string | null;
    installing: boolean;
  } | null;
  /** Which online services have a key (off by default). */
  online: { posters: boolean; subtitles: boolean };
  /** What a phone looks at in the library; the TV page follows it when `seq` changes. */
  view: { path: string; focus: string | null; filter: Filter; seq: number };
  /** The Windows build asks once to add Nanar to the Start menu and the right-click menu. */
  offerIntegration: boolean;
}

export interface Pairing {
  lan: boolean;
  /** "nanar.local:8642" while that name is announced on the network. */
  name: string | null;
  addresses: string[];
  url: string | null;
}

export class ApiError extends Error {
  constructor(public readonly code: string) {
    super(code);
  }
}

async function send(path: string, body: unknown): Promise<void> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { code?: string };
    throw new ApiError(payload.code ?? `http_${response.status}`);
  }
}

/** Plays a video: from `start` (0: from the beginning), or where it was left when omitted. */
export const play = (videoId: string, start?: number) =>
  send('/api/play', { videoId, start: start ?? null });

export const command = (action: string, value?: unknown) =>
  send('/api/command', { action, value: value ?? null });

/** Marks a video watched or not, or takes it out of "À suivre". */
export const mark = (videoId: string, action: 'watched' | 'unwatched' | 'dismiss') =>
  send('/api/mark', { videoId, action });

/** French subtitles from OpenSubtitles for the video playing. */
export const findSubtitles = () => send('/api/subtitles', {});

/** This machine only: opens or closes the PC's own Wi-Fi (mode hôtel). */
export const turnHotspot = (on: boolean) => send('/api/hotspot', { on });

export interface OnlineSettings {
  tmdb: { set: boolean; hint: string | null; error: string | null };
  opensubtitles: { set: boolean; hint: string | null };
}

/** This machine only: looks for new versions once a day (or stops). */
export const setCheckUpdates = (enabled: boolean) => send('/api/updates', { enabled });

/** This machine only: installs the new version; Nanar closes and starts again. */
export const installUpdate = () => send('/api/update', {});

/** This machine only: which online services have a key. */
export async function fetchOnline(): Promise<OnlineSettings> {
  const response = await fetch('/api/online');
  if (!response.ok) throw new ApiError(`http_${response.status}`);
  return (await response.json()) as OnlineSettings;
}

/** This machine only: a new key ("" takes it away), tried before it is kept. */
export const setOnline = (keys: { tmdb?: string; opensubtitles?: string }) =>
  send('/api/online', keys);

export const pair = (key: string) => send('/api/pair', { key });

/** This machine only: asks for a folder with the system's picker, and opens it. */
export const chooseFolder = () => send('/api/open', { choose: true });

/** This machine only: adds (or not) Nanar to the Start menu and the right-click menu. */
export const answerIntegration = (install: boolean) => send('/api/integration', { install });

/** Tells the TV what this phone looks at: the TV page's path ("/", "/g/<id>"), an item, and
 *  what the library shows. */
export const setView = (path: string, focus: string | null = null, filter?: Filter) =>
  send('/api/view', { path, focus, filter });

/** Whether this browser may drive Nanar (a paired phone, or this machine). */
export async function isPaired(): Promise<boolean> {
  const response = await fetch('/api/state');
  if (response.status === 401) return false;
  if (!response.ok) throw new ApiError(`http_${response.status}`);
  return true;
}

export async function fetchPairing(): Promise<Pairing> {
  const response = await fetch('/api/pairing');
  if (!response.ok) throw new ApiError(`http_${response.status}`);
  return (await response.json()) as Pairing;
}

export async function fetchLibrary(): Promise<Library> {
  const response = await fetch('/api/library');
  if (!response.ok) throw new ApiError(`http_${response.status}`);
  return (await response.json()) as Library;
}

/**
 * The library, loaded again whenever `version` changes (the state's `libraryVersion`: new files,
 * thumbnails, what was watched). The previous one stays shown while the new one loads.
 */
export function useLibrary(version?: number): Library | null {
  const [library, setLibrary] = useState<Library | null>(null);
  useEffect(() => {
    let alive = true;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const load = () =>
      fetchLibrary()
        .then((lib) => alive && setLibrary(lib))
        .catch(() => {
          if (alive) retry = setTimeout(load, 2000);
        });
    load();
    return () => {
      alive = false;
      clearTimeout(retry);
    };
  }, [version]);
  return library;
}

export interface Live {
  state: State | null;
  /** False while the connection is down (Nanar closed, the phone off the network). */
  connected: boolean;
}

/**
 * Nanar's state, live. The WebSocket reconnects on its own when the server comes back, and as
 * soon as the page is shown again (phones drop connections of pages in the background).
 */
export function useLive(enabled = true): Live {
  const [live, setLive] = useState<Live>({ state: null, connected: false });
  useEffect(() => {
    if (!enabled) return;
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    const connect = () => {
      clearTimeout(retry);
      const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
      socket = new WebSocket(`${scheme}://${location.host}/api/live`);
      socket.onmessage = (event) => {
        const message = JSON.parse(String(event.data)) as { type: string; state: State };
        if (message.type === 'state') setLive({ state: message.state, connected: true });
      };
      socket.onclose = () => {
        setLive((previous) => ({ ...previous, connected: false }));
        if (!closed) retry = setTimeout(connect, 1500);
      };
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible' && socket?.readyState !== WebSocket.OPEN) {
        if (socket) socket.onclose = null; // no second reconnection from the old one
        socket?.close();
        connect();
      }
    };
    connect();
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      closed = true;
      clearTimeout(retry);
      document.removeEventListener('visibilitychange', onVisible);
      socket?.close();
    };
  }, [enabled]);
  return live;
}
