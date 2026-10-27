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
  playing: Playing | null;
}

export interface Pairing {
  lan: boolean;
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

export const play = (videoId: string, start = 0) => send('/api/play', { videoId, start });

export const command = (action: string, value?: unknown) =>
  send('/api/command', { action, value: value ?? null });

export const pair = (key: string) => send('/api/pair', { key });

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
