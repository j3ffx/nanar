/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

// The API runs in `nanar --dev` (scripts/dev.mjs); in production the Python package serves this build.
const API = `http://127.0.0.1:${process.env.NANAR_PORT ?? 8642}`;

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: API, ws: true } },
  },
  build: {
    outDir: fileURLToPath(new URL('../src/nanar/web/static', import.meta.url)),
    emptyOutDir: true,
  },
  test: { include: ['src/**/*.test.ts'] },
});
