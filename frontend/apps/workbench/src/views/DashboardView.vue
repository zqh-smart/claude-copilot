<script setup lang="ts">
import { Connection, DataBoard, Document, Files } from '@element-plus/icons-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import { useWorkspaceStore } from '@/stores/workspace'

const workspace = useWorkspaceStore()
const { documents, servingEvals: evals } = storeToRefs(workspace)
const loading = ref(!workspace.loadedAt.documents || !workspace.loadedAt.servingEvals)
const error = ref('')

const completed = computed(() => documents.value.filter((item) => item.status === 'completed').length)
const passingEvals = computed(
  () => evals.value.filter((item) => (item.l3?.total || 0) > 0 && item.l3?.pass_rate === 1).length,
)

onMounted(async () => {
  try {
    await Promise.all([workspace.ensureDocuments(), workspace.ensureServingEvals()])
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '后端连接失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="page-stack">
    <div class="hero-panel">
      <div>
        <p class="eyebrow">FINANCIAL DOCUMENT INTELLIGENCE</p>
        <h1>金融知识与研究工作台</h1>
        <p>统一管理文档解析、混合检索、图谱推理、Agentic Research 与正式报告。</p>
      </div>
      <el-button type="primary" size="large" @click="$router.push('/upload')">上传文档</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="warning" show-icon :closable="false" />

    <div class="metric-grid" v-loading="loading">
      <article class="metric-card">
        <el-icon><Files /></el-icon><span>文档总数</span><strong>{{ documents.length }}</strong>
      </article>
      <article class="metric-card">
        <el-icon><Document /></el-icon><span>处理完成</span><strong>{{ completed }}</strong>
      </article>
      <article class="metric-card">
        <el-icon><DataBoard /></el-icon><span>L3 评测</span><strong>{{ evals.length }}</strong>
      </article>
      <article class="metric-card">
        <el-icon><Connection /></el-icon><span>全量通过</span><strong>{{ passingEvals }}</strong>
      </article>
    </div>

    <el-card shadow="never" class="migration-card">
      <template #header><strong>前端形态</strong></template>
      <el-steps :active="2" finish-status="success" align-center>
        <el-step title="管理后台骨架" description="参考 Yudao Lite 工程实践" />
        <el-step title="工作台 9 页" description="REST 页面全部接入" />
        <el-step title="构建隔离" description="本地 PostCSS / Vite 边界" />
        <el-step title="Agent Chat" description="独立 Next.js 应用，协议级兼容" />
      </el-steps>
    </el-card>
  </section>
</template>
