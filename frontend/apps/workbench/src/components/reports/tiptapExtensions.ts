import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'

import AIInsightBlock from '@/components/reports/blocks/AIInsightBlock.vue'
import CitationMark from '@/components/reports/blocks/CitationMark.vue'
import ReportChartBlock from '@/components/reports/blocks/ReportChartBlock.vue'

export const AIInsight = Node.create({
  name: 'aiInsight',
  group: 'block',
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      items: { default: [] },
    }
  },
  parseHTML() {
    return [{ tag: 'div[data-type="ai-insight"]' }]
  },
  renderHTML({ HTMLAttributes }: { HTMLAttributes: Record<string, unknown> }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'ai-insight' })]
  },
  addNodeView() {
    return VueNodeViewRenderer(AIInsightBlock as never)
  },
})

export const ReportChart = Node.create({
  name: 'reportChart',
  group: 'block',
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      id: { default: '' },
      title: { default: '' },
      chartType: { default: 'combo' },
      xAxis: { default: [] },
      series: { default: [] },
      dataSource: { default: '' },
    }
  },
  parseHTML() {
    return [{ tag: 'div[data-type="report-chart"]' }]
  },
  renderHTML({ HTMLAttributes }: { HTMLAttributes: Record<string, unknown> }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'report-chart' })]
  },
  addNodeView() {
    return VueNodeViewRenderer(ReportChartBlock as never)
  },
})

export const Citation = Node.create({
  name: 'citation',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,
  addAttributes() {
    return {
      citationId: { default: '' },
      label: { default: '' },
    }
  },
  parseHTML() {
    return [{ tag: 'span[data-type="citation"]' }]
  },
  renderHTML({ HTMLAttributes }: { HTMLAttributes: Record<string, unknown> }) {
    return ['span', mergeAttributes(HTMLAttributes, { 'data-type': 'citation' }), String(HTMLAttributes.label || '')]
  },
  addNodeView() {
    return VueNodeViewRenderer(CitationMark as never)
  },
})
