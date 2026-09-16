import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const fastApiTarget = env.VITE_FASTAPI_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [
      vue(),
      Components({
        dts: 'src/components.d.ts',
        resolvers: [ElementPlusResolver({ importStyle: 'css' })],
      }),
    ],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    define: {
      // Bake the Agent Chat destination at build time, mirroring the defaults
      // that apps/chat-ui/vite.config.ts bakes for __LANGGRAPH_*. Without this
      // the top-bar handoff falls back to the relative '/chat', which resolves
      // against the workbench origin (:3000) where no /chat route exists, so
      // the button silently lands on a dead URL unless a local .env is present.
      // Dev needs the absolute :3001 URL (no proxy, by design); production is
      // served same-origin under the reverse proxy.
      __CHAT_UI_URL__: JSON.stringify(
        env.VITE_CHAT_UI_URL ||
          (mode === 'development' ? 'http://127.0.0.1:3001/chat/' : '/chat/'),
      ),
    },
    server: {
      proxy: {
        '/api/fastapi': {
          target: fastApiTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/fastapi/, ''),
        },
      },
    },
  }
})
