<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  researchDocument,
  type DocumentSummary,
  type ResearchPreview,
} from '@/api/http'
import { useWorkspaceStore } from '@/stores/workspace'

const suggestions = [
  '2021年营业收入是多少？',
  '净利润及其同比变化如何？',
  '主要风险因素有哪些？',
  '经营活动现金流表现如何？',
]
const route = useRoute()
const workspace = useWorkspaceStore()
const { documents, servingEvals: serving } = storeToRefs(workspace)
const loading = ref(!workspace.loadedAt.documents || !workspace.loadedAt.servingEvals)
const researching = ref(false)
const error = ref('')
const docId = ref('')
const question = ref(suggestions[0])
const result = ref<ResearchPreview | null>(null)
const resultTab = ref('answer')

const servingIds = computed(() => new Set(serving.value.map((item) => item.doc_id)))
const selected = computed(() => documents.value.find((item) => item.doc_id === docId.value) || null)
const selectedEval = computed(() => serving.value.find((item) => item.doc_id === docId.value) || null)
const answer = computed(() => result.value?.synthesis?.answer || result.value?.answer || '暂无合成回答')

function documentLabel(item: DocumentSummary) {
  return `${item.metadata.company || item.filename} · ${item.metadata.year || '—'} · ${item.filename}`
}

function formatValue(value: number | string | null | undefined) {
  if (value == null || value === '') return '—'
  return typeof value === 'number' ? new Intl.NumberFormat('zh-CN').format(value) : value
}

function pageOf(metadata: Record<string, unknown> | undefined) {
  const retrieval = metadata?.retrieval as Record<string, unknown> | undefined
  const page = retrieval?.page ?? metadata?.page
  return typeof page === 'number' ? page : null
}

function retrievalScore(metadata: Record<string, unknown> | undefined, key: string) {
  const retrieval = metadata?.retrieval as Record<string, unknown> | undefined
  const value = retrieval?.[key]
  return typeof value === 'number' ? value.toFixed(3) : '—'
}

function sourceUrl(documentId: string, page: number | null) {
  return `/api/fastapi/api/v1/documents/${encodeURIComponent(documentId)}/source${page ? `#page=${page}` : ''}`
}

async function ask() {
  if (!docId.value || !question.value.trim()) return
  researching.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await researchDocument(docId.value, question.value.trim(), 5)
    resultTab.value = 'answer'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '研究问答失败'
  } finally {
    researching.value = false
  }
}

async function copyAnswer() {
  await navigator.clipboard.writeText(answer.value)
}

onMounted(async () => {
  try {
    await Promise.all([
      workspace.ensureDocuments(),
      workspace.ensureServingEvals().catch(() => []),
    ])
    const pinned = typeof route.query.doc_id === 'string' ? route.query.doc_id : ''
    const preferred =
      documents.value.find((item) => item.doc_id === pinned) ||
      documents.value.find((item) => item.status === 'completed' && servingIds.value.has(item.doc_id)) ||
      documents.value.find((item) => item.status === 'completed' && !/smoke|\.txt$/i.test(item.filename))
    docId.value = preferred?.doc_id || documents.value[0]?.doc_id || ''
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '研究工作台加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="page-stack">
    <div class="page-heading compact-heading">
      <div><p class="eyebrow">AGENTIC RAG</p><h1>研报与文档深度问答</h1><p>向量、结构化指标和知识图谱联合检索，并展示完整证据诊断。</p></div>
      <el-tag type="success" effect="plain">可追溯</el-tag>
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="research-config-grid" v-loading="loading">
      <el-card shadow="never">
        <template #header><strong>文档范围</strong></template>
        <el-select v-model="docId" filterable style="width: 100%">
          <el-option v-for="item in documents" :key="item.doc_id" :label="documentLabel(item)" :value="item.doc_id" />
        </el-select>
        <el-descriptions v-if="selected" :column="2" border class="document-summary">
          <el-descriptions-item label="公司">{{ selected.metadata.company || '—' }}</el-descriptions-item>
          <el-descriptions-item label="年度">{{ selected.metadata.year || '—' }}</el-descriptions-item>
          <el-descriptions-item label="切片">{{ selected.segment_count || 0 }}</el-descriptions-item>
          <el-descriptions-item label="状态"><el-tag :type="servingIds.has(selected.doc_id) ? 'success' : 'warning'">{{ servingIds.has(selected.doc_id) ? 'Serving' : selected.status }}</el-tag></el-descriptions-item>
          <el-descriptions-item v-if="selectedEval?.l3" label="L3 通过率" :span="2">{{ selectedEval.l3.pass_rate == null ? '—' : `${(selectedEval.l3.pass_rate * 100).toFixed(0)}%` }}（{{ selectedEval.l3.passed }}/{{ selectedEval.l3.total }}）</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never">
        <template #header><strong>研究问题</strong></template>
        <el-input v-model="question" type="textarea" :rows="4" placeholder="输入财务、经营或风险问题" />
        <div class="suggestion-list"><el-button v-for="item in suggestions" :key="item" size="small" :type="question === item ? 'primary' : 'default'" plain @click="question = item">{{ item }}</el-button></div>
        <div class="form-submit"><el-button type="primary" :loading="researching" :disabled="!docId || !question.trim()" @click="ask">发起研究检索</el-button></div>
      </el-card>
    </div>

    <template v-if="result">
      <el-card shadow="never">
        <div class="route-strip">
          <span>意图 <b>{{ result.query_analysis?.intent || '—' }}</b></span>
          <el-tag v-for="item in result.query_analysis?.routes || []" :key="item" effect="plain">{{ item }}</el-tag>
          <span>文本 {{ result.hits?.length || 0 }}</span><span>指标 {{ result.metrics?.length || 0 }}</span><span>图路径 {{ result.graph_paths?.length || 0 }}</span>
          <el-tag :type="result.grounded ? 'success' : 'warning'">{{ result.grounded ? '已落地' : '待核验' }}</el-tag>
        </div>
      </el-card>
      <el-alert v-for="warning in result.warnings || []" :key="warning" :title="warning" type="warning" show-icon :closable="false" />

      <el-card shadow="never">
        <el-tabs v-model="resultTab">
          <el-tab-pane label="综合回答" name="answer">
            <div class="answer-toolbar"><span>Agentic RAG 合成结果</span><el-button text type="primary" @click="copyAnswer">复制回答</el-button></div>
            <pre class="research-answer">{{ answer }}</pre>
            <div v-if="result.synthesis?.key_findings?.length" class="highlight-list"><div v-for="item in result.synthesis.key_findings" :key="item" class="highlight-item">✓ {{ item }}</div></div>
            <el-descriptions v-if="result.critic" :column="3" border>
              <el-descriptions-item label="Critic"><el-tag :type="result.critic.passed ? 'success' : 'danger'">{{ result.critic.passed ? 'PASS' : 'REVISE' }}</el-tag></el-descriptions-item>
              <el-descriptions-item label="评分">{{ result.critic.score }}</el-descriptions-item>
              <el-descriptions-item label="说明">{{ result.critic.summary }}</el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>

          <el-tab-pane :label="`文本证据 (${result.hits?.length || 0})`" name="hits">
            <article v-for="hit in result.hits || []" :key="hit.segment_id" class="evidence-card">
              <header><b>{{ hit.segment_id.slice(0, 18) }}</b><span>融合 {{ retrievalScore(hit.metadata, 'fused_score') }} · 向量 {{ retrievalScore(hit.metadata, 'vector_score') }} · 词法 {{ retrievalScore(hit.metadata, 'lexical_score') }}</span></header>
              <p>{{ hit.content }}</p>
              <a :href="sourceUrl(result.doc_id || docId, pageOf(hit.metadata))" target="_blank" rel="noreferrer">查看原文{{ pageOf(hit.metadata) ? ` · 第 ${pageOf(hit.metadata)} 页` : '' }}</a>
            </article>
          </el-tab-pane>

          <el-tab-pane :label="`结构化指标 (${result.metrics?.length || 0})`" name="metrics">
            <el-table :data="result.metrics || []" stripe>
              <el-table-column prop="metric_key" label="指标" width="220" />
              <el-table-column prop="period" label="期间" width="170" />
              <el-table-column label="数值" width="180"><template #default="scope"><b>{{ formatValue(scope.row.value) }}</b> {{ scope.row.unit }} {{ scope.row.currency }}</template></el-table-column>
              <el-table-column prop="entity_scope" label="主体口径" width="140" />
              <el-table-column prop="source_table_title" label="来源表" min-width="260" show-overflow-tooltip />
              <el-table-column label="页码" width="80"><template #default="scope">{{ scope.row.page_range?.[0] || '—' }}</template></el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane :label="`图谱路径 (${result.graph_paths?.length || 0})`" name="graph">
            <el-table :data="result.graph_paths || []" stripe><el-table-column prop="summary" label="关系路径" min-width="500" /><el-table-column prop="score" label="得分" width="110" /></el-table>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </template>
  </section>
</template>
