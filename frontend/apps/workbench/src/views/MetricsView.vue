<script setup lang="ts">
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { init, use, type EChartsType } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { storeToRefs } from 'pinia'
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch, watchEffect } from 'vue'

import {
  getMetricTrend,
  queryMetrics,
  type MetricObservation,
  type MetricTrend,
} from '@/api/http'
import PageToolbar from '@/components/PageToolbar.vue'
import { clearChatLaunchContext, setChatLaunchContext } from '@/lib/chat-launch-context'
import { useWorkspaceStore } from '@/stores/workspace'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const metricOptions = [
  { key: 'revenue', label: '营业收入 Revenue' },
  { key: 'net_income', label: '净利润 Net Income' },
  { key: 'total_assets', label: '资产总计 Total Assets' },
  { key: 'interest_income', label: '利息收入 Interest Income' },
  { key: 'net_cash_from_operating_activities', label: '经营活动现金流' },
]

const workspace = useWorkspaceStore()
const { companies: cachedCompanies } = storeToRefs(workspace)
const loading = ref(!workspace.loadedAt.companies)
const querying = ref(false)
const error = ref('')
const companies = computed(() => cachedCompanies.value.filter((item) => item.metric_count > 0))
const companyId = ref('')
const metricKey = ref('revenue')
const metrics = ref<MetricObservation[]>([])
const trend = ref<MetricTrend | null>(null)
const chartHost = ref<HTMLDivElement | null>(null)
let chart: EChartsType | null = null

const selectedCompany = computed(
  () => companies.value.find((item) => item.company_id === companyId.value) || null,
)
const metricLabel = computed(
  () => metricOptions.find((item) => item.key === metricKey.value)?.label || metricKey.value,
)
const trendAnomaly = computed(() => {
  if (trend.value?.cagr != null && Math.abs(trend.value.cagr) > 1) {
    return '复合增长率超过 100%，趋势中可能混入了错误表格或量纲不一致的观测值，请先核对下方来源。'
  }
  if (trend.value?.points.some((item) => item.yoy_growth != null && Math.abs(item.yoy_growth) > 5)) {
    return '同比变化超过 500%，请先核对期间、单位与来源表，再用于报告结论。'
  }
  return ''
})
const latestPoint = computed(() => trend.value?.points.at(-1) || null)

function formatValue(value: number | string | null | undefined) {
  if (value == null || value === '') return '—'
  if (typeof value === 'number') return new Intl.NumberFormat('zh-CN').format(value)
  const numeric = Number(value)
  return Number.isFinite(numeric) ? new Intl.NumberFormat('zh-CN').format(numeric) : value
}

function formatGrowth(value: number | null | undefined) {
  if (value == null) return '—'
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
}

async function renderChart() {
  await nextTick()
  if (!chartHost.value || !trend.value?.points.length) {
    chart?.dispose()
    chart = null
    return
  }
  chart ||= init(chartHost.value)
  chart.setOption({
    animationDuration: 450,
    color: ['#1a5945'],
    grid: { left: 22, right: 18, top: 28, bottom: 20, containLabel: true },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: unknown) => `${formatValue(value as number)} ${trend.value?.unit || ''}`,
    },
    xAxis: {
      type: 'category',
      data: trend.value.points.map((item) => String(item.year)),
      axisLine: { lineStyle: { color: '#d7e1dc' } },
    },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf2ef' } } },
    series: [
      {
        name: metricLabel.value,
        type: 'bar',
        barMaxWidth: 48,
        data: trend.value.points.map((item) => item.value),
        itemStyle: { borderRadius: [6, 6, 0, 0] },
      },
    ],
  })
}

async function loadMetrics() {
  if (!companyId.value) return
  querying.value = true
  error.value = ''
  try {
    ;[metrics.value, trend.value] = await Promise.all([
      queryMetrics(companyId.value, metricKey.value),
      getMetricTrend(companyId.value, metricKey.value),
    ])
  } catch (reason) {
    metrics.value = []
    trend.value = null
    error.value = reason instanceof Error ? reason.message : '指标数据读取失败'
  } finally {
    querying.value = false
  }
}

function sourceUrl(documentId: string, page?: number | null) {
  return `/api/fastapi/api/v1/documents/${encodeURIComponent(documentId)}/source${page ? `#page=${page}` : ''}`
}

function publishChatContext() {
  setChatLaunchContext(
    companyId.value
      ? {
          source: 'metrics',
          resourceId: companyId.value,
          prompt: `分析${selectedCompany.value?.name || '该公司'}的${metricLabel.value}趋势与数据质量`,
        }
      : undefined,
  )
}

function resizeChart() {
  chart?.resize()
}

watch(trend, () => void renderChart())
watch([companyId, metricKey], () => void loadMetrics())
watchEffect(publishChatContext)
onActivated(publishChatContext)
onDeactivated(clearChatLaunchContext)

onMounted(async () => {
  window.addEventListener('resize', resizeChart)
  try {
    await workspace.ensureCompanies()
    companyId.value = companies.value[0]?.company_id || ''
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '指标中心加载失败'
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  clearChatLaunchContext()
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
})
</script>

<template>
  <section class="cc-page">
    <PageToolbar kicker="指标中心" subtitle="查询标准化指标、年度趋势和可追溯来源，并明确展示数据质量告警。">
      <el-tag effect="plain">{{ companies.length }} 家有效公司</el-tag>
    </PageToolbar>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <el-card shadow="never" class="filter-card" v-loading="loading">
      <el-empty
        v-if="!loading && !companies.length"
        :image-size="72"
        description="暂无已抽取结构化指标的公司；完成文档处理后会自动出现在这里"
      />
      <el-form v-else inline label-position="top" class="filter-form">
        <el-form-item label="目标公司">
          <el-select v-model="companyId" filterable placeholder="选择公司" style="width: 300px">
            <el-option v-for="item in companies" :key="item.company_id" :label="`${item.name} · ${item.metric_count} 指标`" :value="item.company_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="核心指标">
          <el-select v-model="metricKey" style="width: 280px">
            <el-option v-for="item in metricOptions" :key="item.key" :label="item.label" :value="item.key" />
          </el-select>
        </el-form-item>
        <el-form-item class="filter-action"><el-button type="primary" :loading="querying" @click="loadMetrics">查询指标</el-button></el-form-item>
      </el-form>
    </el-card>

    <div class="metric-grid">
      <article class="metric-card"><span>公司主体</span><strong>{{ selectedCompany?.name || '—' }}</strong><small>{{ selectedCompany?.document_count || 0 }} 份入库文档</small></article>
      <article class="metric-card"><span>当前指标</span><strong>{{ metricLabel }}</strong><small>{{ metrics.length }} 条来源观测</small></article>
      <article class="metric-card success"><span>最新值</span><strong>{{ formatValue(latestPoint?.value) }}</strong><small>{{ latestPoint?.year || '—' }} · {{ trend?.unit || '未标单位' }}</small></article>
      <article class="metric-card"><span>CAGR</span><strong>{{ trend?.cagr == null ? '—' : `${(trend.cagr * 100).toFixed(2)}%` }}</strong><small>仅供分析，先检查质量告警</small></article>
      <article class="metric-card"><span>口径</span><strong>{{ trend?.unit || '—' }} {{ trend?.currency || '' }}</strong><small>默认优先合并口径</small></article>
    </div>

    <el-alert v-if="trendAnomaly" :title="trendAnomaly" type="error" show-icon :closable="false" />
    <el-alert
      v-for="warning in trend?.warnings || []"
      :key="warning"
      :title="warning"
      type="warning"
      show-icon
      :closable="false"
    />

    <div class="bi-grid">
      <el-card shadow="never">
        <template #header><strong>{{ metricLabel }} 年度趋势</strong></template>
        <div v-if="trend?.points.length" ref="chartHost" class="metric-chart" />
        <el-empty v-else description="暂无可绘制趋势" />
      </el-card>

      <el-card shadow="never">
        <template #header><strong>年度变化</strong></template>
        <div class="trend-list">
          <div v-for="point in trend?.points || []" :key="`${point.year}-${point.period}`" class="trend-row">
            <span class="year-badge">{{ point.year }}</span>
            <span><b>{{ formatValue(point.value) }}</b><small>{{ point.period }}</small></span>
            <el-tag :type="point.yoy_growth != null && point.yoy_growth < 0 ? 'danger' : 'success'" effect="plain">YoY {{ formatGrowth(point.yoy_growth) }}</el-tag>
          </div>
          <el-empty v-if="!trend?.points.length" :image-size="70" description="暂无年度数据" />
        </div>
      </el-card>
    </div>

    <el-card shadow="never">
      <template #header><strong>观测值与来源（{{ metrics.length }}）</strong></template>
      <el-table :data="metrics" stripe max-height="520">
        <el-table-column prop="period" label="期间" width="170" />
        <el-table-column label="数值" width="160"><template #default="scope"><b>{{ formatValue(scope.row.value) }}</b> {{ scope.row.unit }} {{ scope.row.currency }}</template></el-table-column>
        <el-table-column prop="entity_scope" label="主体口径" width="140" />
        <el-table-column prop="source_table_title" label="来源表" min-width="260" show-overflow-tooltip />
        <el-table-column label="页码" width="90"><template #default="scope">{{ scope.row.page_range?.[0] || '—' }}</template></el-table-column>
        <el-table-column label="文档" width="150"><template #default="scope">{{ scope.row.document_id.slice(0, 12) }}</template></el-table-column>
        <el-table-column label="溯源" width="90">
          <template #default="scope">
            <el-link
              :href="sourceUrl(scope.row.document_id, scope.row.page_range?.[0])"
              target="_blank"
              type="primary"
            >
              打开来源
            </el-link>
          </template>
        </el-table-column>
        <template #empty><el-empty description="当前公司与指标没有可用观测值" /></template>
      </el-table>
    </el-card>
  </section>
</template>
