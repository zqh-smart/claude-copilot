/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_FASTAPI_TARGET?: string
  readonly VITE_CHAT_UI_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/**
 * Agent Chat destination, baked by `define` in vite.config.ts so the handoff
 * works without a local `.env`. See `apps/workbench/vite.config.ts`.
 */
declare const __CHAT_UI_URL__: string
