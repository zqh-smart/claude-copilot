<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import {
  getServingEval,
  listScorecards,
  type ScorecardSummary,
  type ServingEvalSummary,
} from '@/api/http'
import { useWorkspaceStore } from '@/stores/workspace'

const workspace = useWorkspaceStore()
const { servingEvals: reports } = storeToRefs(workspace)
const loading = ref(!workspace.loadedAt.servingEvals)
const detailLoading = ref(false)
const error = ref('')
const scorecards = ref<ScorecardSummary[]>([])
const selected = ref<ServingEvalSummary | null>(null)

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

function percent(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
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
  <section class="page-stack">
    <div class="page-heading compact-heading">
      <div><p class="eyebrow">QUALITY GATES</p><h1>L3 检索与入库门禁</h1><p>查看真实 Serving 报告、案例结果与阶段 Scorecard。</p></div>
      <el-tag type="success" effect="plain">{{ reports.length }} 份报告</el-tag>
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

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
          <el-table-column label="检查" width="190">
            <template #default="scope">路由 {{ scope.row.route_ok ? '✓' : '✗' }} · 指标 {{ scope.row.metric_ok ? '✓' : '✗' }} · 图 {{ scope.row.graph_ok ? '✓' : '✗' }}</template>
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
      </el-table>
    </el-card>
  </section>
</template>
