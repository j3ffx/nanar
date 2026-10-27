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
}

export interface Group {
  id: string;
  kind: 'saga' | 'series';
  title: string;
  videos: string[];
}

export interface Library {
  root: string;
  videos: Record<string, Video>;
  groups: Record<string, Group>;
  entries: { kind: 'video' | 'group'; id: string }[];
}

export interface Track {
  id: number;
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
  playing: Playing | null;
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

export const play = (videoId: string, start = 0) => send('/api/play', { videoId, start });

export const command = (action: string, value?: unknown) =>
  send('/api/command', { action, value: value ?? null });

export async function fetchLibrary(): Promise<Library> {
  const response = await fetch('/api/library');
  if (!response.ok) throw new ApiError(`http_${response.status}`);
  return (await response.json()) as Library;
}

/** The library, loaded once. */
export function useLibrary(): Library | null {
  const [library, setLibrary] = useState<Library | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      fetchLibrary()
        .then((lib) => alive && setLibrary(lib))
        .catch(() => alive && setTimeout(load, 2000));
    load();
    return () => {
      alive = false;
    };
  }, []);
  return library;
}

/** Nanar's state, live: the WebSocket reconnects on its own when the server comes back. */
export function useLiveState(): State | null {
  const [state, setState] = useState<State | null>(null);
  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    const connect = () => {
      const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
      socket = new WebSocket(`${scheme}://${location.host}/api/live`);
      socket.onmessage = (event) => {
        const message = JSON.parse(String(event.data)) as { type: string; state: State };
        if (message.type === 'state') setState(message.state);
      };
      socket.onclose = () => {
        if (!closed) retry = setTimeout(connect, 1000);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, []);
  return state;
}
