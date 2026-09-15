<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import {
  compareDocuments,
  getPortfolioDashboard,
  type CompareResponse,
  type DocumentSummary,
  type PortfolioDashboard,
} from '@/api/http'
import { useWorkspaceStore } from '@/stores/workspace'

const workspace = useWorkspaceStore()
const { documents: cachedDocuments, companies: cachedCompanies } = storeToRefs(workspace)
const loading = ref(!workspace.loadedAt.documents || !workspace.loadedAt.companies)
const comparing = ref(false)
const portfolioLoading = ref(false)
const error = ref('')
const docA = ref('')
const docB = ref('')
const question = ref('比较两份文档的核心财务指标与风险差异')
const period = ref('2021')
const metricKeys = ref('revenue,net_income,net_cash_from_operating_activities')
const comparison = ref<CompareResponse | null>(null)
const portfolio = ref<PortfolioDashboard | null>(null)

const documents = computed(() =>
  cachedDocuments.value.filter(
    (item) => item.status === 'completed' && item.segment_count && !/smoke|worker-soak|\.txt$/i.test(item.filename),
  ),
)
const companies = computed(() => cachedCompanies.value.filter((item) => item.metric_count > 0))

const matrixColumns = computed(() =>
  Array.from(new Set((comparison.value?.matrix || []).flatMap((row) => Object.keys(row)))),
)
const portfolioIds = computed(() => companies.value.slice(0, 4).map((item) => item.company_id))

function docLabel(doc: DocumentSummary) {
  return `${doc.metadata.company || doc.filename} · ${doc.metadata.year || '—'} · ${doc.filename}`
}

function displayValue(value: unknown) {
  if (value == null || value === '') return '—'
  if (typeof value === 'number') return new Intl.NumberFormat('zh-CN').format(value)
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

function parsedMetricKeys() {
  return metricKeys.value.split(',').map((item) => item.trim()).filter(Boolean)
}

function findComparablePair(items: DocumentSummary[]) {
  for (let left = 0; left < items.length; left += 1) {
    for (let right = left + 1; right < items.length; right += 1) {
      const a = items[left]
      const b = items[right]
      if (
        a.metadata.year &&
        a.metadata.year === b.metadata.year &&
        a.metadata.company &&
        b.metadata.company &&
        a.metadata.company !== b.metadata.company
      ) {
        return [a, b] as const
      }
    }
  }
  return [items[0], items[1]] as const
}

async function runCompare() {
  if (!docA.value || !docB.value || docA.value === docB.value) return
  comparing.value = true
  error.value = ''
  try {
    comparison.value = await compareDocuments({
      doc_id_a: docA.value,
      doc_id_b: docB.value,
      question: question.value.trim(),
      period: period.value.trim() || null,
      metric_keys: parsedMetricKeys(),
      use_workflow: true,
    })
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '文档对比失败'
  } finally {
    comparing.value = false
  }
}

async function loadPortfolio() {
  if (portfolioIds.value.length < 2) return
  portfolioLoading.value = true
  try {
    portfolio.value = await getPortfolioDashboard(portfolioIds.value, [
      'revenue',
      'net_income',
      'total_assets',
    ])
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '组合概览加载失败'
  } finally {
    portfolioLoading.value = false
  }
}

onMounted(async () => {
  try {
    await Promise.all([workspace.ensureDocuments(), workspace.ensureCompanies()])
    const [firstDocument, secondDocument] = findComparablePair(documents.value)
    docA.value = firstDocument?.doc_id || ''
    docB.value = secondDocument?.doc_id || ''
    period.value = String(firstDocument?.metadata.year || period.value)
    await loadPortfolio()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '对比中心加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="page-stack">
    <div class="page-heading compact-heading">
      <div><p class="eyebrow">COMPARATIVE RESEARCH</p><h1>文档与投资组合对比</h1><p>双文档工作流生成差异矩阵，组合视图汇总指标排名与图谱风险。</p></div>
      <el-tag effect="plain">{{ documents.length }} 份可比文档</el-tag>
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <el-card shadow="never" v-loading="loading">
      <template #header><strong>双文档对比设定</strong></template>
      <el-form label-position="top">
        <div class="compare-doc-grid">
          <el-form-item label="基准文档 A"><el-select v-model="docA" filterable style="width: 100%"><el-option v-for="item in documents" :key="item.doc_id" :label="docLabel(item)" :value="item.doc_id" /></el-select></el-form-item>
          <el-form-item label="对比文档 B"><el-select v-model="docB" filterable style="width: 100%"><el-option v-for="item in documents" :key="item.doc_id" :label="docLabel(item)" :value="item.doc_id" /></el-select></el-form-item>
        </div>
        <el-form-item label="研究问题"><el-input v-model="question" /></el-form-item>
        <div class="compare-doc-grid">
          <el-form-item label="报告期间"><el-input v-model="period" placeholder="例如 2021" /></el-form-item>
          <el-form-item label="指标 Keys（逗号分隔）"><el-input v-model="metricKeys" /></el-form-item>
        </div>
        <div class="form-submit"><el-button type="primary" :loading="comparing" :disabled="!docA || !docB || docA === docB" @click="runCompare">开始两文对比</el-button></div>
      </el-form>
    </el-card>

    <el-card v-if="comparison" shadow="never">
      <template #header><div class="card-title"><strong>对比分析结果</strong><el-tag effect="plain">{{ comparison.workflow }}</el-tag></div></template>
      <div class="comparison-grid">
        <div>
          <pre class="answer-panel">{{ comparison.answer_markdown }}</pre>
          <div v-if="comparison.highlights.length" class="highlight-list">
            <div v-for="item in comparison.highlights" :key="item" class="highlight-item">✓ {{ item }}</div>
          </div>
          <el-alert v-for="warning in comparison.warnings" :key="warning" :title="warning" type="warning" :closable="false" show-icon />
        </div>
        <el-table :data="comparison.matrix" stripe max-height="520">
          <el-table-column v-for="column in matrixColumns" :key="column" :label="column" min-width="145">
            <template #default="scope">{{ displayValue(scope.row[column]) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card shadow="never" v-loading="portfolioLoading">
      <template #header><div class="card-title"><strong>组合概览</strong><el-button text type="primary" @click="loadPortfolio">刷新组合</el-button></div></template>
      <template v-if="portfolio">
        <div class="portfolio-rankings">
          <article v-for="ranking in portfolio.rankings" :key="ranking.metric_key" class="ranking-card">
            <header>{{ ranking.metric_key }}</header>
            <div v-for="(item, index) in ranking.items" :key="item.company_id" class="ranking-row">
              <span>{{ index + 1 }}. {{ item.company_name }}</span><b>{{ displayValue(item.value) }} {{ item.unit || '' }}</b>
            </div>
          </article>
        </div>
        <h3 class="section-title">图谱风险热力</h3>
        <el-table :data="portfolio.risk_heatmap" stripe>
          <el-table-column prop="company_name" label="公司" min-width="180" />
          <el-table-column prop="total" label="风险因子" width="110" />
          <el-table-column label="分类" min-width="420"><template #default="scope"><el-tag v-for="(count, category) in scope.row.categories" :key="category" effect="plain" class="risk-tag">{{ category }}: {{ count }}</el-tag></template></el-table-column>
        </el-table>
        <el-alert v-for="warning in portfolio.warnings" :key="warning" :title="warning" type="warning" :closable="false" show-icon />
      </template>
      <el-empty v-else description="至少需要两家有结构化指标的公司" />
    </el-card>
  </section>
</template>
