/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// AUTHORITY / RECONCILIATION:
// Vite resolves config files in this order: vite.config.js, vite.config.mjs,
// vite.config.ts, ... so vite.config.js is the EFFECTIVE runtime config and this
// vite.config.ts is the TypeScript source of record. They MUST stay behaviorally
// identical. Port resolution rules mirror chakraops/app/core/chakraops_ports.py
// and scripts/chakraops_ports.ps1.

const __dirname = fileURLToPath(new URL('.', import.meta.url))

const MIN_PORT = 1
const MAX_PORT = 65535
const DEFAULT_BACKEND_PORT = 18800
const DEFAULT_FRONTEND_PORT = 18873

function resolvePort(raw: string | undefined, envName: string, def: number): number {
  if (raw === undefined || raw.trim() === '') return def
  const t = raw.trim()
  if (!/^\d+$/.test(t)) {
    throw new Error(`${envName}="${raw}" is not a valid port (must be an integer ${MIN_PORT}-${MAX_PORT})`)
  }
  const n = Number(t)
  if (n < MIN_PORT || n > MAX_PORT) {
    throw new Error(`${envName}=${n} is out of range (${MIN_PORT}-${MAX_PORT})`)
  }
  return n
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendPort = resolvePort(env.CHAKRAOPS_BACKEND_PORT, 'CHAKRAOPS_BACKEND_PORT', DEFAULT_BACKEND_PORT)
  const frontendPort = resolvePort(env.CHAKRAOPS_FRONTEND_PORT, 'CHAKRAOPS_FRONTEND_PORT', DEFAULT_FRONTEND_PORT)
  if (backendPort === frontendPort) {
    throw new Error(`Backend and frontend ports must differ (both=${backendPort}); set distinct CHAKRAOPS_BACKEND_PORT/CHAKRAOPS_FRONTEND_PORT`)
  }

  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: frontendPort,
      strictPort: true,
      proxy: {
        // 127.0.0.1 avoids Windows localhost → ::1 where Docker may own another :8000 listener.
        '/api': `http://127.0.0.1:${backendPort}`,
      },
    },
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src'),
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.{test,spec}.{ts,tsx}'],
    },
  }
})
