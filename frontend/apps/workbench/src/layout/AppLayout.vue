<script setup lang="ts">
import { ChatDotRound, Expand, Fold } from '@element-plus/icons-vue'
import { computed, ref, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import GlobalSearch, { type SearchEntry } from '@/components/GlobalSearch.vue'
import { groupKeyForPath, homeNavItem, navGroups } from '@/constants/nav'
import { buildAgentChatUrl } from '@/lib/agent-chat'
import { useChatLaunchContext } from '@/lib/chat-launch-context'
import { prefetchWorkspaceView } from '@/router'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const app = useAppStore()
const chatUiUrl = __CHAT_UI_URL__
const chatLaunchContext = useChatLaunchContext()
const openeds = ref<string[]>([])

const active = computed(() => {
  const path = route.path
  if (path === '/') return '/'
  return `/${path.split('/')[1]}`
})
const pageTitle = computed(() => String(route.meta.title || '工作台'))

const searchEntries = computed<SearchEntry[]>(() => {
  const items: SearchEntry[] = [
    {
      path: homeNavItem.path,
      title: homeNavItem.title,
      group: '导航',
      keywords: homeNavItem.keywords,
    },
    {
      path: '__agent_chat__',
      title: 'Agent Chat',
      group: '对话',
      keywords: ['agent', 'langgraph', '研究助手'],
    },
  ]
  for (const group of navGroups) {
    for (const item of group.items) {
      items.push({
        path: item.path,
        title: item.title,
        group: group.title,
        keywords: item.keywords,
      })
    }
  }
  return items
})

function openAgentChat() {
  window.location.assign(buildAgentChatUrl(chatUiUrl, chatLaunchContext.value))
}

function onSearchNavigate(entry: SearchEntry) {
  if (entry.path === '__agent_chat__') openAgentChat()
}

function ensureGroupOpen(key: string | null) {
  if (key && !openeds.value.includes(key)) {
    openeds.value = [...openeds.value, key]
  }
}

watch(
  () => route.path,
  (path) => ensureGroupOpen(groupKeyForPath(path)),
  { immediate: true },
)

function prefetch(path: string) {
  prefetchWorkspaceView(path)
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ 'sidebar--collapsed': app.collapsed }">
      <div class="sidebar__brand">
        <span class="sidebar__logo-mark">CC</span>
        <span v-if="!app.collapsed" class="sidebar__logo">Claude Copilot</span>
      </div>

      <el-scrollbar class="sidebar__scroll">
        <el-menu
          :default-active="active"
          v-model:openeds="openeds"
          :collapse="app.collapsed"
          :collapse-transition="false"
          router
          class="sidebar__menu"
        >
          <el-menu-item :index="homeNavItem.path" @mouseenter="prefetch(homeNavItem.path)">
            <el-icon><component :is="homeNavItem.icon" /></el-icon>
            <template #title>{{ homeNavItem.title }}</template>
          </el-menu-item>

          <el-sub-menu v-for="group in navGroups" :key="group.key" :index="group.key">
            <template #title>
              <el-icon><component :is="group.icon" /></el-icon>
              <span>{{ group.title }}</span>
            </template>
            <el-menu-item
              v-for="item in group.items"
              :key="item.path"
              :index="item.path"
              @mouseenter="prefetch(item.path)"
            >
              <template #title>{{ item.title }}</template>
            </el-menu-item>
          </el-sub-menu>
        </el-menu>
      </el-scrollbar>

      <button type="button" class="sidebar__toggle" aria-label="切换侧栏" @click="app.toggleSidebar">
        <el-icon><component :is="app.collapsed ? Expand : Fold" /></el-icon>
        <span v-if="!app.collapsed">收起导航</span>
      </button>
    </aside>

    <div class="workspace">
      <header class="workspace__header">
        <div class="workspace__header-left">
          <h1 class="workspace__title">{{ pageTitle }}</h1>
        </div>
        <div class="workspace__header-right">
          <GlobalSearch :entries="searchEntries" @navigate="onSearchNavigate" />
          <el-button type="primary" @click="openAgentChat">
            <el-icon><ChatDotRound /></el-icon>
            Agent Chat
          </el-button>
        </div>
      </header>
      <main class="workspace__main">
        <div class="workspace__content">
          <RouterView v-slot="{ Component }">
            <KeepAlive :max="8">
              <component :is="Component" />
            </KeepAlive>
          </RouterView>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  gap: var(--cc-shell-gap);
  height: 100vh;
  padding: var(--cc-shell-pad);
  box-sizing: border-box;
  background: #ffffff;
  color: var(--cc-text-primary);
}

.sidebar {
  --sidebar-pad-x: 12px;
  display: flex;
  flex-direction: column;
  width: var(--cc-sidebar-width);
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid var(--cc-border-light);
  border-radius: var(--cc-radius-lg);
  background: var(--cc-bg-sidebar);
  box-shadow: var(--cc-shadow-xs);
  transition: width 0.2s ease;
}

.sidebar--collapsed {
  width: var(--cc-sidebar-collapsed-width);
}

.sidebar__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 60px;
  padding: 0 calc(var(--sidebar-pad-x) + 4px);
}

.sidebar__logo-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 36px;
  padding: 0 6px;
  border-radius: 11px;
  background: linear-gradient(135deg, var(--cc-brand-primary) 0%, #2f7a5f 100%);
  color: #fff;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}

.sidebar__logo {
  color: var(--cc-text-primary);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  white-space: nowrap;
}

.sidebar__scroll {
  flex: 1;
  min-height: 0;
}

.sidebar__menu {
  --el-menu-base-level-padding: 12px;
  --el-menu-level-padding: 18px;
  --el-menu-item-height: 42px;
  --el-menu-sub-item-height: 38px;
  padding: 8px var(--sidebar-pad-x) 16px;
  border-right: none;
  background: transparent;
}

.sidebar__menu :deep(.el-menu-item),
.sidebar__menu :deep(.el-sub-menu__title) {
  height: 42px;
  margin-bottom: 4px;
  border-radius: 11px;
  color: var(--cc-text-secondary);
  font-weight: 500;
  line-height: 42px;
}

.sidebar__menu :deep(.el-menu-item .el-icon),
.sidebar__menu :deep(.el-sub-menu__title .el-icon) {
  margin-right: 10px;
  font-size: 17px;
}

.sidebar__menu :deep(.el-menu-item.is-active) {
  background: var(--cc-brand-soft);
  color: var(--cc-brand-primary);
  font-weight: 600;
}

.sidebar__menu :deep(.el-menu-item:hover),
.sidebar__menu :deep(.el-sub-menu__title:hover) {
  background: var(--cc-bg-hover);
  color: var(--cc-text-primary);
}

.sidebar__menu :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
  color: var(--cc-brand-primary);
  font-weight: 600;
}

.sidebar__menu :deep(.el-sub-menu .el-menu) {
  padding: 2px 0 6px;
  background: transparent;
}

.sidebar__menu :deep(.el-sub-menu .el-menu-item) {
  min-width: auto;
  height: 38px;
  padding-left: calc(var(--el-menu-base-level-padding) + 28px) !important;
  font-size: 13px;
  line-height: 38px;
}

.sidebar__toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: var(--sidebar-pad-x);
  padding: 10px 12px;
  border: 1px solid var(--cc-border-light);
  border-radius: 11px;
  background: var(--cc-bg-card);
  color: var(--cc-text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.sidebar__toggle:hover {
  border-color: var(--cc-border-color);
  background: var(--cc-bg-hover);
}

.sidebar--collapsed .sidebar__toggle {
  padding: 10px 0;
}

.workspace {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--cc-border-light);
  border-radius: var(--cc-radius-xl);
  background: var(--cc-bg-page);
  box-shadow: var(--cc-shadow-xs);
}

.workspace__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 64px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--cc-border-light);
}

.workspace__header-left,
.workspace__header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.workspace__title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.02em;
}

.workspace__main {
  flex: 1;
  overflow: auto;
}

.workspace__content {
  width: 100%;
  max-width: var(--cc-content-max-width);
  padding: 20px 24px 28px;
}

@media (max-width: 768px) {
  .app-shell {
    flex-direction: column;
    gap: 8px;
    padding: 8px;
  }

  .sidebar,
  .sidebar--collapsed {
    width: 100%;
  }

  .sidebar {
    max-height: 42vh;
  }

  .sidebar--collapsed {
    max-height: 60px;
  }

  .workspace__header {
    flex-wrap: wrap;
    padding: 12px 16px;
  }

  .workspace__content {
    padding: 16px;
  }
}
</style>
