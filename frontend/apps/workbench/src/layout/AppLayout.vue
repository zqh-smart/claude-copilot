<script setup lang="ts">
import {
  DataAnalysis,
  Document,
  ChatDotRound,
  Files,
  Fold,
  Histogram,
  HomeFilled,
  Memo,
  Operation,
  Search,
  Setting,
  UploadFilled,
} from '@element-plus/icons-vue'
import { computed } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import { prefetchWorkspaceView } from '@/router'
import { useAppStore } from '@/stores/app'
import { buildAgentChatUrl } from '@/lib/agent-chat'

const route = useRoute()
const router = useRouter()
const app = useAppStore()
const chatUiUrl = import.meta.env.VITE_CHAT_UI_URL || '/chat'

// 完整 Agent Chat 由独立 Next.js 应用提供；工作台只通过业务上下文与其交接。
const menus = [
  { path: '/', label: '工作台', icon: HomeFilled },
  { path: '/knowledge', label: '知识库', icon: Files },
  { path: '/research', label: '研究问答', icon: Search },
  { path: '/compare', label: '对比分析', icon: DataAnalysis },
  { path: '/reports', label: '报告中心', icon: Memo },
  { path: '/metrics', label: '指标中心', icon: Histogram },
  { path: '/eval', label: '评测中心', icon: Operation },
  { path: '/jobs', label: '任务中心', icon: Setting },
  { path: '/upload', label: '文档上传', icon: UploadFilled },
  { path: '/chat-memory', label: '对话记忆', icon: Document },
]

const activePath = computed(() => (route.path === '/' ? '/' : `/${route.path.split('/')[1]}`))

function openAgentChat() {
  window.location.assign(buildAgentChatUrl(chatUiUrl))
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside :width="app.collapsed ? '72px' : '232px'" class="sidebar">
      <div class="brand" :class="{ compact: app.collapsed }">
        <span class="brand-mark">CC</span>
        <span v-if="!app.collapsed" class="brand-copy">
          <strong>Claude Copilot</strong>
          <small>金融文档智能</small>
        </span>
      </div>
      <el-menu
        :default-active="activePath"
        :collapse="app.collapsed"
        :collapse-transition="false"
        background-color="transparent"
        text-color="#b9cec6"
        active-text-color="#ffffff"
        router
      >
        <el-menu-item
          v-for="item in menus"
          :key="item.path"
          :index="item.path"
          @mouseenter="prefetchWorkspaceView(item.path)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.label }}</template>
        </el-menu-item>
      </el-menu>
      <div v-if="!app.collapsed" class="sidebar-foot">Vue 3 + Vite · Element Plus</div>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <el-button text circle aria-label="切换侧栏" @click="app.toggleSidebar">
          <el-icon size="19"><Fold /></el-icon>
        </el-button>
        <div class="breadcrumb">
          <span>Claude Copilot</span>
          <b>/</b>
          <strong>{{ route.meta.title }}</strong>
        </div>
        <div class="topbar-actions">
          <el-button type="primary" plain @click="openAgentChat">
            <el-icon><ChatDotRound /></el-icon>
            Agent Chat
          </el-button>
          <el-tag type="success" effect="plain" round>开发环境</el-tag>
          <el-avatar :size="34">AI</el-avatar>
        </div>
      </el-header>
      <el-main class="workspace">
        <RouterView v-slot="{ Component }">
          <KeepAlive :max="8">
            <component :is="Component" />
          </KeepAlive>
        </RouterView>
      </el-main>
    </el-container>
  </el-container>
</template>
