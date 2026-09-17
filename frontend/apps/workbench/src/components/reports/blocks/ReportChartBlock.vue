<script setup lang="ts">
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { init, use, type EChartsType } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { NodeViewWrapper } from '@tiptap/vue-3'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { ReportChartSeries } from '@/types/report'

use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{
  node: {
    attrs: {
      id?: string
      title?: string
      chartType?: string
      xAxis?: string[]
      series?: ReportChartSeries[]
      dataSource?: string
    }
  }
  selected: boolean
}>()

const host = ref<HTMLDivElement | null>(null)
let chart: EChartsType | null = null
let observer: ResizeObserver | null = null

const title = computed(() => String(props.node.attrs.title || '未命名图表'))
const xAxis = computed(() => (Array.isArray(props.node.attrs.xAxis) ? props.node.attrs.xAxis : []))
const series = computed(() => (Array.isArray(props.node.attrs.series) ? props.node.attrs.series : []))

function renderChart() {
  if (!host.value || host.value.clientWidth < 8) return
  chart ||= init(host.value)
  chart.resize()
  chart.setOption({
    color: ['#1a5945', '#c9943b', '#5b8c7a'],
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 48, right: 48, top: 36, bottom: 28 },
    xAxis: { type: 'category', data: xAxis.value, axisLine: { lineStyle: { color: '#d7e0db' } } },
    yAxis: [
      { type: 'value', splitLine: { lineStyle: { color: '#eef2f0' } } },
      { type: 'value', min: 0, max: 40, axisLabel: { formatter: '{value}%' }, splitLine: { show: false } },
    ],
    series: series.value.map((item) => ({
      name: item.name,
      type: item.type,
      data: item.data,
      yAxisIndex: item.yAxisIndex || 0,
      barMaxWidth: 28,
      smooth: true,
    })),
  })
}

onMounted(async () => {
  await nextTick()
  renderChart()
  observer = new ResizeObserver(() => renderChart())
  if (host.value) observer.observe(host.value)
})
watch(() => [xAxis.value, series.value], renderChart, { deep: true })
onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  chart?.dispose()
  chart = null
})
</script>

<template>
  <node-view-wrapper class="report-chart-block" :class="{ 'is-selected': selected }" data-drag-handle>
    <div class="report-chart-block__head">
      <strong>{{ title }}</strong>
      <small v-if="node.attrs.dataSource">{{ node.attrs.dataSource }}</small>
    </div>
    <div ref="host" class="report-chart-block__canvas" />
  </node-view-wrapper>
</template>

<style scoped>
.report-chart-block {
  margin: 18px 0;
  padding: 12px 12px 8px;
  border: 1px solid #e6ece9;
  border-radius: 12px;
  background: #fff;
}
.report-chart-block.is-selected {
  border-color: var(--cc-brand-muted);
}
.report-chart-block__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 0 4px 8px;
}
.report-chart-block__head strong {
  font-size: 13px;
}
.report-chart-block__head small {
  color: var(--cc-text-muted);
  font-size: 11px;
}
.report-chart-block__canvas {
  width: 100%;
  height: 240px;
}
</style>
