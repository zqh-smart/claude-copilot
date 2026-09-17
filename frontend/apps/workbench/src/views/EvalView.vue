<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import {
  getServingEval,
  listScorecards,
  type RetrievalCase,
  type ScorecardSummary,
  type ServingEvalSummary,
} from '@/api/http'
import PageToolbar from '@/components/PageToolbar.vue'
import { useWorkspaceStore } from '@/stores/workspace'

const workspace = useWorkspaceStore()
const { servingEvals: reports } = storeToRefs(workspace)
const loading = ref(!workspace.loadedAt.servingEvals)
const detailLoading = ref(false)
const error = ref('')
const scorecards = ref<ScorecardSummary[]>([])
const selected = ref<ServingEvalSummary | null>(null)

const overview = computed(() => {
  const total = reports.value.reduce((sum, item) => sum + (item.l3?.total || 0), 0)
  const passed = reports.value.reduce((sum, item) => sum + (item.l3?.passed || 0), 0)
  const allowing = scorecards.value.filter(
    (item) => item.serving_gate?.allow_metric_serving,
  ).length
  return {
    total,
    passed,
    failed: Math.max(total - passed, 0),
    passRate: total ? passed / total : 0,
    allowing,
  }
})

const stats = computed(() => {
  const cases = selected.value?.cases || []
  const total = cases.length
  const passed = cases.filter((item) => item.passed).length
  return {
    total,
    passed,
    failed: total - passed,
    route: total ? cases.filter((item) => item.route_ok).length / total : 0,
    metric: total ? cases.filter((item) => item.metric_ok).length / total : 0,
  }
})

async function openReport(docId: string) {
  detailLoading.value = true
  error.value = ''
  try {
    selected.value = await getServingEval(docId)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '评测报告读取失败'
  } finally {
    detailLoading.value = false
  }
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const [, nextScorecards] = await Promise.all([
      workspace.ensureServingEvals(true),
      listScorecards(),
    ])
    scorecards.value = nextScorecards
    const current =
      reports.value.find((item) => item.doc_id === selected.value?.doc_id) ||
      reports.value.find((item) => (item.l3?.total || 0) > 0) ||
      reports.value[0]
    selected.value = null
    if (current) await openReport(current.doc_id)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '评测中心刷新失败'
  } finally {
    loading.value = false
  }
}

function percent(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function matchedMetric(item: RetrievalCase) {
  if (!item?.matched_metric) return '—'
  const { metric_key, period, value } = item.matched_metric
  return [metric_key, period, value].filter((part) => part != null && part !== '').join(' · ') || '—'
}

onMounted(async () => {
  try {
    ;[, scorecards.value] = await Promise.all([
      workspace.ensureServingEvals(),
      listScorecards().catch(() => []),
    ])
    const firstEvaluated = reports.value.find((item) => (item.l3?.total || 0) > 0)
    const initial = firstEvaluated || reports.value[0]
    if (initial) await openReport(initial.doc_id)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '评测中心加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="cc-page">
    <PageToolbar kicker="评测中心" subtitle="查看真实 Serving 报告、案例结果与阶段 Scorecard。">
      <el-tag type="success" effect="plain">{{ reports.length }} 份报告</el-tag>
      <el-button :loading="loading" @click="refresh">刷新评测</el-button>
    </PageToolbar>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="overview-kpis">
      <article class="overview-kpi overview-kpi--static">
        <div class="overview-kpi__head"><span>评测案例</span></div>
        <div class="overview-kpi__value">{{ overview.total }}</div>
        <p class="overview-kpi__meta">{{ reports.length }} 份 Serving 报告</p>
      </article>
      <article class="overview-kpi overview-kpi--static overview-kpi--success">
        <div class="overview-kpi__head"><span>案例通过</span></div>
        <div class="overview-kpi__value">{{ overview.passed }}</div>
        <p class="overview-kpi__meta">通过率 {{ percent(overview.passRate) }}</p>
      </article>
      <article class="overview-kpi overview-kpi--static" :class="{ 'overview-kpi--danger': overview.failed > 0 }">
        <div class="overview-kpi__head"><span>待修复案例</span></div>
        <div class="overview-kpi__value">{{ overview.failed }}</div>
        <p class="overview-kpi__meta">路由、指标或图谱检查未通过</p>
      </article>
      <article class="overview-kpi overview-kpi--static">
        <div class="overview-kpi__head"><span>Serving Gate</span></div>
        <div class="overview-kpi__value">{{ overview.allowing }} / {{ scorecards.length }}</div>
        <p class="overview-kpi__meta">允许指标服务的阶段报告</p>
      </article>
    </div>

    <el-card shadow="never" v-loading="loading">
      <div class="report-pills">
        <el-button
          v-for="item in reports"
          :key="item.doc_id"
          :type="selected?.doc_id === item.doc_id ? 'primary' : 'default'"
          @click="openReport(item.doc_id)"
        >
          {{ item.doc_id.slice(0, 10) }} · {{ item.l3?.passed || 0 }}/{{ item.l3?.total || 0 }}
        </el-button>
      </div>
      <el-empty
        v-if="!reports.length && !loading"
        :image-size="72"
        description="暂无 Serving 评测报告；先运行评测流水线生成报告"
      />
    </el-card>

    <template v-if="selected">
      <div class="metric-grid" v-loading="detailLoading">
        <article class="metric-card"><span>总案例</span><strong>{{ stats.total }}</strong></article>
        <article class="metric-card success"><span>通过</span><strong>{{ stats.passed }}</strong></article>
        <article class="metric-card danger"><span>失败</span><strong>{{ stats.failed }}</strong></article>
        <article class="metric-card"><span>路由准确率</span><strong>{{ percent(stats.route) }}</strong></article>
        <article class="metric-card"><span>指标准确率</span><strong>{{ percent(stats.metric) }}</strong></article>
      </div>

      <el-card shadow="never" v-loading="detailLoading">
        <template #header><strong>评测案例 · {{ selected.doc_id }}</strong></template>
        <el-table :data="selected.cases || []" stripe max-height="520">
          <el-table-column label="状态" width="90">
            <template #default="scope"><el-tag :type="scope.row.passed ? 'success' : 'danger'">{{ scope.row.passed ? 'PASS' : 'FAIL' }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="id" label="Case" width="190" show-overflow-tooltip />
          <el-table-column prop="question" label="问题" min-width="330" show-overflow-tooltip />
          <el-table-column prop="expect_route" label="期望路由" width="110" />
          <el-table-column prop="actual_intent" label="实际意图" width="110" />
          <el-table-column label="匹配指标" min-width="210" show-overflow-tooltip>
            <template #default="scope">{{ matchedMetric(scope.row) }}</template>
          </el-table-column>
          <el-table-column label="检查" width="245">
            <template #default="scope">路由 {{ scope.row.route_ok ? '✓' : '✗' }} · 指标 {{ scope.row.metric_ok ? '✓' : '✗' }} · 语义 {{ scope.row.semantic_ok ? '✓' : '✗' }} · 图 {{ scope.row.graph_ok ? '✓' : '✗' }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <el-card shadow="never">
      <template #header><strong>阶段 Scorecard</strong></template>
      <el-table :data="scorecards" stripe>
        <el-table-column prop="name" label="报告" min-width="250" />
        <el-table-column label="核心指标准确率" width="160"><template #default="scope">{{ percent(scope.row.summary_scores?.core_metric_exact_match) }}</template></el-table-column>
        <el-table-column label="来源落地率" width="150"><template #default="scope">{{ percent(scope.row.summary_scores?.source_grounding_rate) }}</template></el-table-column>
        <el-table-column label="Serving Gate" width="140"><template #default="scope"><el-tag :type="scope.row.serving_gate?.allow_metric_serving ? 'success' : 'danger'">{{ scope.row.serving_gate?.allow_metric_serving ? 'ALLOW' : 'BLOCK' }}</el-tag></template></el-table-column>
        <el-table-column label="阻塞原因" min-width="260" show-overflow-tooltip>
          <template #default="scope">{{ scope.row.serving_gate?.failures?.join('；') || '—' }}</template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!scorecards.length && !loading"
        :image-size="64"
        description="暂无阶段 Scorecard"
      />
    </el-card>
  </section>
</template>
