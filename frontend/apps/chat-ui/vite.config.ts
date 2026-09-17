import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// React + Vite + assistant-ui Agent Chat surface.
//
// `base: '/chat/'` is the single source of truth for the URL contract.
// Dev server runs on http://127.0.0.1:3001 with the application mounted at
// /chat/, so the canonical local URL is http://127.0.0.1:3001/chat/. In
// production the Workbench reverse-proxies /chat/** to this build artifact
// (see frontend/ARCHITECTURE.md).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    base: '/chat/',
    plugins: [react()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      // Listen on 127.0.0.1:3001 with the app mounted at /chat/. The
      // canonical local URL is http://127.0.0.1:3001/chat/.
      port: 3001,
      strictPort: true,
      host: '127.0.0.1',
      open: '/chat/',
    },
    preview: {
      port: 3001,
      strictPort: true,
      open: '/chat/',
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
    define: {
      // Surface backend defaults so the assistant-ui LangChain runtime can
      // talk to the local LangGraph dev server out of the box. Only public,
      // non-secret values are allowed through this seam.
      __LANGGRAPH_API_URL__: JSON.stringify(
        env.VITE_LANGGRAPH_API_URL || 'http://127.0.0.1:2025',
      ),
      __LANGGRAPH_ASSISTANT_ID__: JSON.stringify(
        env.VITE_LANGGRAPH_ASSISTANT_ID || 'agent',
      ),
    },
  }
})