import { useEffect, useState } from 'react';

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
}

export interface Library {
  root: string;
  videos: Record<string, Video>;
  groups: Record<string, Group>;
  entries: { kind: 'video' | 'group'; id: string }[];
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
  /** What a phone looks at in the library; the TV page follows it when `seq` changes. */
  view: { path: string; focus: string | null; seq: number };
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

export const pair = (key: string) => send('/api/pair', { key });

/** This machine only: asks for a folder with the system's picker, and opens it. */
export const chooseFolder = () => send('/api/open', { choose: true });

/** This machine only: adds (or not) Nanar to the Start menu and the right-click menu. */
export const answerIntegration = (install: boolean) => send('/api/integration', { install });

/** Tells the TV what this phone looks at: the TV page's path ("/", "/g/<id>") and an item. */
export const setView = (path: string, focus: string | null = null) =>
  send('/api/view', { path, focus });

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
