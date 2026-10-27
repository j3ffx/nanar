#!/usr/bin/env node
// `npm run dev`: Nanar in demo mode, its window showing the pages from Vite (hot reload).
// Python changes need a restart (the window lives in the same process as the server).
import { spawn } from 'node:child_process';

const port = process.env.NANAR_PORT ?? '8642';
const env = { ...process.env, NANAR_PORT: port };
const run = (command, args) =>
  spawn(command, args, { env, stdio: 'inherit', shell: process.platform === 'win32' });

const vite = run('npm', ['run', 'dev', '-w', 'web']);
// Give Vite a moment, so that the window doesn't open on an empty page.
setTimeout(() => {
  const nanar = run('uv', ['run', 'nanar', '--demo', '--dev', '--port', port]);
  nanar.on('exit', () => vite.kill());
  process.on('SIGINT', () => nanar.kill());
}, 1500);
