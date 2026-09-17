<script setup lang="ts">
import { Connection, DataBoard, Document, Files } from '@element-plus/icons-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

import PageToolbar from '@/components/PageToolbar.vue'
import { useAsyncLoad } from '@/composables/useAsyncLoad'
import { useWorkspaceStore } from '@/stores/workspace'

const router = useRouter()
const workspace = useWorkspaceStore()
const { documents, servingEvals: evals } = storeToRefs(workspace)
const { loading, error, run } = useAsyncLoad()

const completed = computed(() => documents.value.filter((item) => item.status === 'completed').length)
const passingEvals = computed(
  () => evals.value.filter((item) => (item.l3?.total || 0) > 0 && item.l3?.pass_rate === 1).length,
)
const failed = computed(() => documents.value.filter((item) => item.status === 'failed').length)
const completionRate = computed(() =>
  documents.value.length ? Math.round((completed.value / documents.value.length) * 100) : 0,
)
const recentDocuments = computed(() => documents.value.slice(0, 6))

function statusType(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  return 'warning'
}

onMounted(() => {
  void run(async () => {
    await Promise.all([workspace.ensureDocuments(), workspace.ensureServingEvals()])
  })
})
</script>

<template>
  <section class="cc-page" v-loading="loading">
    <PageToolbar kicker="金融文档智能" subtitle="文档解析、混合检索、图谱推理与正式报告的统一入口。">
      <el-button @click="router.push('/knowledge')">打开知识库</el-button>
      <el-button type="primary" @click="router.push('/upload')">上传文档</el-button>
    </PageToolbar>

    <el-alert v-if="error" :title="error" type="warning" show-icon :closable="false" />

    <section class="overview-kpis">
      <article class="overview-kpi" @click="router.push('/knowledge')">
        <div class="overview-kpi__head">
          <span>文档总数</span>
          <el-icon><Files /></el-icon>
        </div>
        <div class="overview-kpi__value">{{ documents.length }}</div>
        <p class="overview-kpi__meta">知识库可检索资产</p>
      </article>
      <article class="overview-kpi overview-kpi--success" @click="router.push('/jobs')">
        <div class="overview-kpi__head">
          <span>处理完成</span>
          <el-icon><Document /></el-icon>
        </div>
        <div class="overview-kpi__value">
          {{ completed }}
          <small>/ {{ documents.length }}</small>
        </div>
        <div class="overview-kpi__progress"><span :style="{ width: `${completionRate}%` }" /></div>
        <p class="overview-kpi__meta">完成率 {{ completionRate }}%</p>
      </article>
      <article class="overview-kpi overview-kpi--warning" @click="router.push('/eval')">
        <div class="overview-kpi__head">
          <span>L3 评测</span>
          <el-icon><DataBoard /></el-icon>
        </div>
        <div class="overview-kpi__value">{{ evals.length }}</div>
        <p class="overview-kpi__meta">全量通过 {{ passingEvals }}</p>
      </article>
      <article class="overview-kpi" :class="{ 'overview-kpi--danger': failed > 0 }" @click="router.push('/jobs')">
        <div class="overview-kpi__head">
          <span>失败文档</span>
          <el-icon><Connection /></el-icon>
        </div>
        <div class="overview-kpi__value">{{ failed }}</div>
        <p class="overview-kpi__meta">需在任务中心重试或排查</p>
      </article>
    </section>

    <div class="home-board">
      <article class="cc-card">
        <div class="cc-card__head">
          <div>
            <h2 class="cc-card__title">最近文档</h2>
            <p class="cc-card__sub">从知识库继续切片、召回或研究问答</p>
          </div>
          <el-button link type="primary" @click="router.push('/knowledge')">查看全部</el-button>
        </div>
        <el-empty v-if="!recentDocuments.length" description="还没有文档，先上传一份年报" :image-size="72" />
        <button
          v-for="item in recentDocuments"
          :key="item.doc_id"
          type="button"
          class="home-doc-row"
          @click="router.push({ path: '/knowledge', query: { doc_id: item.doc_id } })"
        >
          <span>
            <strong>{{ item.metadata.company || item.filename }}</strong>
            <small>{{ item.metadata.year || '—' }} · {{ item.segment_count || 0 }} 切片</small>
          </span>
          <el-tag size="small" :type="statusType(item.status)">{{ item.status }}</el-tag>
        </button>
      </article>

      <article class="cc-card">
        <div class="cc-card__head">
          <div>
            <h2 class="cc-card__title">快捷入口</h2>
            <p class="cc-card__sub">工作台负责业务页，Agent Chat 仍走独立 React 应用</p>
          </div>
        </div>
        <nav class="home-shortcuts">
          <button type="button" @click="router.push('/research')">研究问答</button>
          <button type="button" @click="router.push('/compare')">对比分析</button>
          <button type="button" @click="router.push('/reports')">报告中心</button>
          <button type="button" @click="router.push('/metrics')">指标中心</button>
          <button type="button" @click="router.push('/eval')">评测中心</button>
          <button type="button" @click="router.push('/chat-memory')">对话记忆</button>
        </nav>
      </article>
    </div>
  </section>
</template>
