<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import {
  getChatMemoryHealth,
  getChatMemoryLayer,
  searchChatMemory,
  type ChatMemoryHealth,
  type ChatMemoryLayer,
} from '@/api/http'

const layers: Array<{ id: ChatMemoryLayer; label: string; hint: string }> = [
  { id: 'L0', label: '原始对话', hint: '完整会话消息' },
  { id: 'L1', label: '原子事实', hint: '从对话提取的稳定事实' },
  { id: 'L2', label: '场景记忆', hint: '任务与场景级经验' },
  { id: 'L3', label: '用户画像', hint: '长期偏好与画像' },
]

const loading = ref(true)
const error = ref('')
const health = ref<ChatMemoryHealth | null>(null)
const layer = ref<ChatMemoryLayer>('L1')
const items = ref<Array<Record<string, unknown>>>([])
const total = ref(0)
const selectedIndex = ref(-1)
const query = ref('')
const sessionId = ref('')
const searchMode = ref(false)

const selected = computed(() => items.value[selectedIndex.value] || null)
const connected = computed(() => health.value?.status === 'up' || health.value?.status === 'ok')

function rawString(item: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = item[key]
    if (value != null && String(value).trim()) return String(value)
  }
  return ''
}

function itemTitle(item: Record<string, unknown>, index: number) {
  const value = rawString(item, ['title', 'content', 'text', 'summary', 'path', 'role', 'name'])
  if (!value) return `记忆条目 ${index + 1}`
  const oneLine = value.replace(/\s+/g, ' ').trim()
  return oneLine.length > 72 ? `${oneLine.slice(0, 72)}…` : oneLine
}

function itemSummary(item: Record<string, unknown>) {
  const value = rawString(item, ['summary', 'content', 'text', 'description', 'snippet'])
  if (!value) return '暂无摘要'
  const oneLine = value.replace(/\s+/g, ' ').trim()
  return oneLine.length > 180 ? `${oneLine.slice(0, 180)}…` : oneLine
}

function itemId(item: Record<string, unknown>, index: number) {
  return rawString(item, ['id', 'message_id', 'memory_id', 'path']) || `memory-${index + 1}`
}

function itemLayer(item: Record<string, unknown>) {
  const value = rawString(item, ['layer', 'memory_layer', 'level'])
  return /^L[0-3]$/.test(value) ? value : layer.value
}

function itemTime(item: Record<string, unknown>) {
  const value = rawString(item, ['timestamp', 'created_at', 'updated_at', 'captured_at'])
  if (!value) return '—'
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? value : new Date(parsed).toLocaleString('zh-CN', { hour12: false })
}

function itemConfidence(item: Record<string, unknown>) {
  const value = item.confidence ?? item.score ?? item.relevance
  if (typeof value === 'number') return value <= 1 ? `${(value * 100).toFixed(1)}%` : value.toFixed(3)
  return value == null ? '—' : String(value)
}

async function loadLayer() {
  loading.value = true
  error.value = ''
  searchMode.value = false
  try {
    const response = await getChatMemoryLayer(layer.value, { sessionId: sessionId.value.trim() })
    items.value = response.items || []
    total.value = response.total ?? items.value.length
    selectedIndex.value = items.value.length ? 0 : -1
  } catch (reason) {
    items.value = []
    error.value = reason instanceof Error ? reason.message : '记忆层读取失败'
  } finally {
    loading.value = false
  }
}

async function runSearch() {
  if (!query.value.trim()) {
    await loadLayer()
    return
  }
  loading.value = true
  error.value = ''
  try {
    const response = await searchChatMemory(query.value.trim(), sessionId.value.trim())
    items.value = response.items || []
    total.value = response.total ?? items.value.length
    selectedIndex.value = items.value.length ? 0 : -1
    searchMode.value = true
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '记忆搜索失败'
  } finally {
    loading.value = false
  }
}

async function copyJson() {
  if (selected.value) await navigator.clipboard.writeText(JSON.stringify(selected.value, null, 2))
}

function downloadJson() {
  if (!selected.value) return
  const blob = new Blob([JSON.stringify(selected.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `chat-memory-${itemId(selected.value, selectedIndex.value)}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

watch(layer, () => void loadLayer())

onMounted(async () => {
  try {
    health.value = await getChatMemoryHealth()
  } catch (reason) {
    health.value = { status: 'down', error: reason instanceof Error ? reason.message : String(reason) }
  }
  await loadLayer()
})
</script>

<template>
  <section class="page-stack">
    <div class="page-heading compact-heading">
      <div><p class="eyebrow">CONVERSATION MEMORY</p><h1>对话记忆</h1><p>L0–L3 会话经验与用户偏好；与金融文档三库相互独立。</p></div>
      <el-tag :type="connected ? 'success' : health?.status === 'disabled' ? 'warning' : 'danger'" effect="plain">{{ connected ? 'MemoryCore 已连接' : health?.status === 'disabled' ? 'MemoryCore 未启用' : 'MemoryCore 不可用' }}</el-tag>
    </div>
    <el-alert v-if="health?.status === 'disabled'" title="后端 CHAT_MEMORY_ENABLED=false。启用 MemoryCore sidecar 后，此页面会自动显示真实记忆。" type="warning" show-icon :closable="false" />
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <el-card shadow="never">
      <div class="memory-toolbar">
        <el-radio-group v-model="layer">
          <el-radio-button v-for="item in layers" :key="item.id" :value="item.id">{{ item.id }} {{ item.label }}</el-radio-button>
        </el-radio-group>
        <el-input v-model="sessionId" clearable placeholder="按 session_id / thread_id 筛选" />
        <el-input v-model="query" clearable placeholder="搜索记忆内容或关键词" @keyup.enter="runSearch" />
        <el-button type="primary" :loading="loading" @click="runSearch">搜索</el-button>
        <el-button v-if="searchMode" @click="query = ''; loadLayer()">退出搜索</el-button>
      </div>
    </el-card>

    <div class="memory-grid" v-loading="loading">
      <el-card shadow="never" class="memory-list-card">
        <template #header><div class="card-title"><strong>{{ layers.find((item) => item.id === layer)?.hint }}</strong><span>{{ total }} 条</span></div></template>
        <button v-for="(item, index) in items" :key="itemId(item, index)" class="memory-row" :class="{ active: selectedIndex === index }" @click="selectedIndex = index">
          <span><b>{{ itemTitle(item, index) }}</b><small>{{ itemSummary(item) }}</small><em>{{ itemTime(item) }}</em></span><el-tag size="small" effect="plain">{{ itemLayer(item) }}</el-tag>
        </button>
        <el-empty v-if="!items.length" description="暂无记忆条目；可在 Agent Chat 多轮对话后生成" />
      </el-card>

      <el-card shadow="never" class="memory-detail-card">
        <template v-if="selected">
          <div class="memory-detail-heading"><div><p class="eyebrow">{{ itemLayer(selected) }}</p><h2>{{ itemTitle(selected, selectedIndex) }}</h2><p>{{ itemSummary(selected) }}</p></div><div><el-button @click="copyJson">复制 JSON</el-button><el-button @click="downloadJson">下载</el-button></div></div>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="记忆 ID">{{ itemId(selected, selectedIndex) }}</el-descriptions-item>
            <el-descriptions-item label="层级">{{ itemLayer(selected) }}</el-descriptions-item>
            <el-descriptions-item label="亲源会话">{{ rawString(selected, ['session_id', 'session_key', 'conversation_id', 'thread_id']) || '—' }}</el-descriptions-item>
            <el-descriptions-item label="置信度">{{ itemConfidence(selected) }}</el-descriptions-item>
          </el-descriptions>
          <pre class="memory-json">{{ JSON.stringify(selected, null, 2) }}</pre>
          <el-alert title="此处是对话记忆，不是年报三库知识。文档证据请前往知识库。" type="info" :closable="false" show-icon />
        </template>
        <el-empty v-else description="请选择一条记忆查看详情" />
      </el-card>
    </div>
  </section>
</template>
