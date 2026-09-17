import { ElMessage } from 'element-plus'
import 'element-plus/theme-chalk/el-message.css'
import 'element-plus/theme-chalk/el-message-box.css'
import '@claude-copilot/design-tokens/tokens.css'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import './styles/index.css'

const app = createApp(App)

app.config.errorHandler = (reason) => {
  const message = reason instanceof Error ? reason.message : '页面发生未知错误'
  ElMessage.error(message)
}

app.use(createPinia()).use(router).mount('#app')
