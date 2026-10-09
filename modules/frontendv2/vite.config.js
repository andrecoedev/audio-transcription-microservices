/* eslint-env node */
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'
import { firebaseWebEnv } from './config/firebaseWebEnv.js'

const frontendRoot = path.dirname(fileURLToPath(import.meta.url))

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Never broaden envPrefix or serialize loadEnv/process.env into the bundle.
  const prefixes = ['VITE_FIREBASE_', 'FIREBASE_']
  const web = firebaseWebEnv(
    loadEnv(mode, path.resolve(frontendRoot, '../backend'), prefixes),
    loadEnv(mode, frontendRoot, prefixes),
    process.env,
  )
  return {
    define: Object.fromEntries(Object.entries(web).map(([key, value]) =>
      [`import.meta.env.${key}`, JSON.stringify(value)])),
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(frontendRoot, './src'),
      },
    },
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: 'http://localhost:2020',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
    test: {
      environment: 'jsdom',
    },
  }
})
