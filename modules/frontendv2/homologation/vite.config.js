/* eslint-env node */
// Explicit test entrypoint: never loaded by production vite.config.js.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
const root = fileURLToPath(new URL('../', import.meta.url))
const fakeAuth = fileURLToPath(new URL('./firebaseDouble.js', import.meta.url))
export default defineConfig({
  root,
  envDir: false,
  define: { 'import.meta.env.VITE_API_URL': JSON.stringify('http://127.0.0.1:2029') },
  plugins: [react(), { name: 'synthetic-firebase-boundary', enforce: 'pre',
    resolveId(source) { if (/\/firebaseAuth$/.test(source)) return fakeAuth } }],
  server: { host: '127.0.0.1', port: 4180, strictPort: true },
})
