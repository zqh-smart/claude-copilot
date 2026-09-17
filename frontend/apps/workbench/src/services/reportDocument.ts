import type { EditorJSON, EditorJSONNode, ReportChartBlock, ReportType } from '@/types/report'

export function textNode(text: string, marks?: EditorJSONNode['marks']): EditorJSONNode {
  return marks?.length ? { type: 'text', text, marks } : { type: 'text', text }
}

export function paragraph(text: string, extra: EditorJSONNode[] = []): EditorJSONNode {
  const content: EditorJSONNode[] = text ? [textNode(text), ...extra] : extra
  return { type: 'paragraph', content: content.length ? content : undefined }
}

export function heading(level: 1 | 2 | 3, text: string): EditorJSONNode {
  return { type: 'heading', attrs: { level }, content: [textNode(text)] }
}

export function citationNode(id: string, label: string): EditorJSONNode {
  return { type: 'citation', attrs: { citationId: id, label } }
}

export function bulletList(items: string[]): EditorJSONNode {
  return {
    type: 'bulletList',
    content: items.map((item) => ({
      type: 'listItem',
      content: [paragraph(item)],
    })),
  }
}

export function tableCell(text: string, header = false): EditorJSONNode {
  return {
    type: header ? 'tableHeader' : 'tableCell',
    content: [paragraph(text)],
  }
}

export function financialTable(headers: string[], rows: string[][]): EditorJSONNode {
  return {
    type: 'table',
    content: [
      { type: 'tableRow', content: headers.map((cell) => tableCell(cell, true)) },
      ...rows.map((row) => ({ type: 'tableRow', content: row.map((cell) => tableCell(cell)) })),
    ],
  }
}

export function aiInsight(items: string[]): EditorJSONNode {
  return { type: 'aiInsight', attrs: { items } }
}

export function reportChart(chart: ReportChartBlock): EditorJSONNode {
  return { type: 'reportChart', attrs: { ...chart } }
}

export function emptyDoc(): EditorJSON {
  return { type: 'doc', content: [paragraph('')] }
}

export function catlH1Document(): EditorJSON {
  return {
    type: 'doc',
    content: [
      heading(1, '宁德时代2026年H1财报分析'),
      paragraph('全球动力电池龙头，盈利能力保持韧性，海外业务加速拓展'),
      heading(2, '一、核心结论'),
      {
        type: 'paragraph',
        content: [
          textNode(
            '2026年上半年，宁德时代实现营业收入1,884.2亿元，同比增长12.7%；归母净利润228.7亿元，同比增长10.3%。公司在国内动力电池市场保持领先地位，同时海外业务持续放量，盈利能力整体保持韧性。',
          ),
          citationNode('c1', '1'),
        ],
      },
      aiInsight([
        '营收和利润保持双位数增长，符合市场预期',
        '海外市场成为重要增长驱动力',
        '毛利率小幅下滑，主要受原材料价格波动影响',
        '整体财务状况稳健，维持“增持”评级',
      ]),
      heading(2, '二、主要财务数据'),
      heading(3, '2.1 核心财务指标'),
      financialTable(
        ['指标（亿元）', '2026H1', '2025H1', '同比变化'],
        [
          ['营业收入', '1,884.2', '1,672.1', '+12.7%'],
          ['归母净利润', '228.7', '207.3', '+10.3%'],
          ['毛利率', '23.5%', '25.1%', '-1.6pct'],
          ['净利率', '12.1%', '12.4%', '-0.3pct'],
          ['经营活动现金流', '356.8', '298.1', '+19.7%'],
        ],
      ),
      heading(3, '2.2 营收与净利润趋势'),
      reportChart({
        id: 'chart-catl-trend',
        title: '营收与净利润趋势',
        chartType: 'combo',
        xAxis: ['2022', '2023', '2024', '2025', '2026H1'],
        series: [
          { name: '营业收入', type: 'bar', data: [3286, 4009, 4270, 4620, 1884] },
          { name: '归母净利润', type: 'bar', data: [307, 441, 507, 530, 229] },
          { name: '毛利率', type: 'line', data: [20.4, 22.9, 24.5, 24.0, 23.5], yAxisIndex: 1 },
        ],
        dataSource: '公司公告 / 年报与半年报',
      }),
    ],
  }
}

export function skeletonDocument(title: string, chapters: string[]): EditorJSON {
  return {
    type: 'doc',
    content: [
      heading(1, title),
      paragraph('正在根据所选材料生成初稿，可随时开始编辑。'),
      ...chapters.flatMap((chapter) => [
        heading(2, chapter),
        paragraph('生成中...'),
      ]),
    ],
  }
}

export function defaultChapters(type: ReportType): string[] {
  if (type === 'peer') return ['对比口径', '核心指标对比', '差异拆解', '结论与建议']
  if (type === 'industry') return ['行业景气', '竞争格局', '公司定位', '风险提示']
  if (type === 'event') return ['事件概述', '财务与业务影响', '后续跟踪']
  return ['核心结论', '主要财务数据', '业务分析', '风险提示']
}

export function extractPlainText(node: EditorJSON | EditorJSONNode | undefined): string {
  if (!node) return ''
  if ('text' in node && node.text) return node.text
  return (node.content || []).map(extractPlainText).join('')
}

export function contentToSectionPayload(doc: EditorJSON): Array<{ title: string; content: string }> {
  const sections: Array<{ title: string; content: string }> = []
  let current = { title: '正文', content: '' }
  for (const node of doc.content || []) {
    if (node.type === 'heading') {
      if (current.content.trim()) sections.push(current)
      current = { title: extractPlainText(node) || '未命名章节', content: '' }
      continue
    }
    const text = extractPlainText(node).trim()
    if (text) current.content += `${text}\n\n`
  }
  if (current.content.trim() || !sections.length) sections.push(current)
  return sections
}
