/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// AUTHORITY / RECONCILIATION:
// Vite resolves config files in this order: vite.config.js, vite.config.mjs,
// vite.config.ts, ... so THIS vite.config.js is the EFFECTIVE runtime config and
// vite.config.ts is the TypeScript source of record. They MUST stay behaviorally
// identical. Port resolution rules mirror chakraops/app/core/chakraops_ports.py
// and scripts/chakraops_ports.ps1.

var __dirname = fileURLToPath(new URL('.', import.meta.url));

var MIN_PORT = 1;
var MAX_PORT = 65535;
var DEFAULT_BACKEND_PORT = 18800;
var DEFAULT_FRONTEND_PORT = 18873;

function resolvePort(raw, envName, def) {
    if (raw === undefined || raw.trim() === '') return def;
    var t = raw.trim();
    if (!/^\d+$/.test(t)) {
        throw new Error(envName + '="' + raw + '" is not a valid port (must be an integer ' + MIN_PORT + '-' + MAX_PORT + ')');
    }
    var n = Number(t);
    if (n < MIN_PORT || n > MAX_PORT) {
        throw new Error(envName + '=' + n + ' is out of range (' + MIN_PORT + '-' + MAX_PORT + ')');
    }
    return n;
}

export default defineConfig(function (_a) {
    var mode = _a.mode;
    var env = loadEnv(mode, process.cwd(), '');
    var backendPort = resolvePort(env.CHAKRAOPS_BACKEND_PORT, 'CHAKRAOPS_BACKEND_PORT', DEFAULT_BACKEND_PORT);
    var frontendPort = resolvePort(env.CHAKRAOPS_FRONTEND_PORT, 'CHAKRAOPS_FRONTEND_PORT', DEFAULT_FRONTEND_PORT);
    if (backendPort === frontendPort) {
        throw new Error('Backend and frontend ports must differ (both=' + backendPort + '); set distinct CHAKRAOPS_BACKEND_PORT/CHAKRAOPS_FRONTEND_PORT');
    }
    return {
        plugins: [react()],
        server: {
            host: '127.0.0.1',
            port: frontendPort,
            strictPort: true,
            proxy: {
                '/api': "http://127.0.0.1:".concat(backendPort),
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
    };
});
