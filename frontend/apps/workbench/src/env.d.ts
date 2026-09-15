/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_FASTAPI_TARGET?: string
  readonly VITE_CHAT_UI_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
