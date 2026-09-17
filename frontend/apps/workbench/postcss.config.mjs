// Vue 子项目自身的 PostCSS 边界。
// 不引入任何插件：Vite 在缺少本地配置时会向上读取 `frontend/postcss.config.mjs`
// （那是 Next.js + Tailwind 的旧配置，与 Vue 子项目无关）。
// 这里显式给一份"空插件"配置，把构建边界锁死在 vue-app/ 之内。
export default {
  plugins: {},
}
