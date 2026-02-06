/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_MODE?: string;
  /** Phase 7: Password/token to unlock app (access gate). If unset, no gate. */
  readonly VITE_APP_PASSWORD?: string;
  /** Phase 7: API base URL (e.g. https://your-app.railway.app). Empty = use relative /api (proxy or same origin). */
  readonly VITE_API_BASE_URL?: string;
  /** Phase 7: API key sent as X-API-Key. Must match CHAKRAOPS_API_KEY on backend. */
  readonly VITE_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
