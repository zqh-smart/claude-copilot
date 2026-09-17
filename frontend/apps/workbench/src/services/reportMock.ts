import { catlH1Document, emptyDoc } from '@/services/reportDocument'
import type { Report } from '@/types/report'

const now = '2026-09-17T14:30:00+08:00'
const earlier = (iso: string) => iso

function version(id: string, reportId: string, createdAt: string, type: Report['versions'][number]['type'], description: string) {
  return { id, reportId, createdAt, type, description }
}

export const MOCK_CURRENT_USER = 'me'

export function seedReports(): Report[] {
  const catlId = 'rpt-catl-2026h1'
  return [
    {
      id: catlId,
      title: '宁德时代2026H1财报分析',
      type: 'earnings',
      company: '宁德时代',
      status: 'draft',
      createdAt: '2026-09-17T10:20:00+08:00',
      updatedAt: now,
      createdBy: MOCK_CURRENT_USER,
      templateId: 'earnings',
      sourceIds: ['src-catl-h1', 'src-catl-annual', 'src-citic', 'src-industry'],
      content: catlH1Document(),
      language: 'zh',
      length: 'standard',
      prompt: '重点分析盈利能力、现金流、海外业务与风险因素',
      citations: [
        {
          id: 'c1',
          reportId: catlId,
          sourceId: 'src-catl-h1',
          sourceTitle: '宁德时代2026年半年度报告.pdf',
          page: 38,
          quote: '2026年上半年营业收入1,884.2亿元，同比增长12.7%。',
          origin: '公司公告',
        },
        {
          id: 'c2',
          reportId: catlId,
          sourceId: 'src-catl-annual',
          sourceTitle: '宁德时代2025年度报告.pdf',
          page: 42,
          quote: '2025年全年归母净利润保持稳健增长。',
          origin: '公司公告',
        },
        {
          id: 'c3',
          reportId: catlId,
          sourceId: 'src-citic',
          sourceTitle: '中信证券：宁德时代深度报告.pdf',
          page: 12,
          quote: '海外产能释放有望成为下一阶段增长主线。',
          origin: '券商研报',
        },
      ],
      relatedSources: [
        { id: 'src-catl-h1', title: '宁德时代2026年半年度报告.pdf', origin: '公司公告', page: 38, date: '2026-08-30', kind: '2026半年报' },
        { id: 'src-catl-annual', title: '宁德时代2025年度报告.pdf', origin: '公司公告', page: 42, date: '2026-03-28', kind: '2025年报' },
        { id: 'src-citic', title: '中信证券：宁德时代深度报告.pdf', origin: '券商研报', date: '2026-09-01', kind: '券商研报' },
        { id: 'src-industry', title: '新能源汽车行业研究框架.pdf', origin: '行业研究', date: '2026-08-20', kind: '行业报告' },
      ],
      versions: [
        version('v3', catlId, '2026-09-17T14:32:00+08:00', 'autosave', '自动保存'),
        version('v2', catlId, '2026-09-17T14:21:00+08:00', 'ai', 'AI修改：财务分析'),
        version('v1', catlId, '2026-09-17T14:05:00+08:00', 'generate', '初始生成'),
      ],
    },
    {
      id: 'rpt-byd-2025',
      title: '比亚迪2025年度经营分析',
      type: 'company',
      company: '比亚迪',
      status: 'draft',
      createdAt: earlier('2026-09-16T10:12:00+08:00'),
      updatedAt: earlier('2026-09-16T10:12:00+08:00'),
      createdBy: MOCK_CURRENT_USER,
      templateId: 'company',
      sourceIds: [],
      content: {
        type: 'doc',
        content: [
          { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: '比亚迪2025年度经营分析' }] },
          { type: 'paragraph', content: [{ type: 'text', text: '草稿：可继续完善销量结构、海外出口与毛利率变化。' }] },
        ],
      },
      language: 'zh',
      length: 'standard',
      prompt: '',
      citations: [],
      relatedSources: [],
      versions: [version('v1', 'rpt-byd-2025', '2026-09-16T10:12:00+08:00', 'generate', '初始生成')],
    },
    {
      id: 'rpt-nev-industry',
      title: '新能源汽车行业深度报告',
      type: 'industry',
      company: '新能源汽车',
      status: 'done',
      createdAt: earlier('2026-09-15T09:00:00+08:00'),
      updatedAt: earlier('2026-09-15T18:20:00+08:00'),
      createdBy: MOCK_CURRENT_USER,
      templateId: 'industry',
      sourceIds: [],
      content: {
        type: 'doc',
        content: [
          { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: '新能源汽车行业深度报告' }] },
          { type: 'paragraph', content: [{ type: 'text', text: '行业景气、竞争格局与龙头公司定位的研究底稿。' }] },
        ],
      },
      language: 'zh',
      length: 'long',
      prompt: '',
      citations: [],
      relatedSources: [],
      versions: [version('v1', 'rpt-nev-industry', '2026-09-15T18:20:00+08:00', 'manual', '定稿')],
    },
    {
      id: 'rpt-midea-peer',
      title: '美的集团同业对比分析',
      type: 'peer',
      company: '美的集团',
      status: 'done',
      createdAt: earlier('2026-09-14T11:00:00+08:00'),
      updatedAt: earlier('2026-09-14T16:40:00+08:00'),
      createdBy: MOCK_CURRENT_USER,
      templateId: 'peer',
      sourceIds: [],
      content: {
        type: 'doc',
        content: [
          { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: '美的集团同业对比分析' }] },
          { type: 'paragraph', content: [{ type: 'text', text: '与格力、海尔在盈利能力与现金流质量上的对比底稿。' }] },
        ],
      },
      language: 'zh',
      length: 'standard',
      prompt: '',
      citations: [],
      relatedSources: [],
      versions: [version('v1', 'rpt-midea-peer', '2026-09-14T16:40:00+08:00', 'manual', '定稿')],
    },
    {
      id: 'rpt-catl-event',
      title: '宁德时代投资观点更新',
      type: 'event',
      company: '宁德时代',
      status: 'archived',
      createdAt: earlier('2026-09-08T09:30:00+08:00'),
      updatedAt: earlier('2026-09-08T15:10:00+08:00'),
      createdBy: MOCK_CURRENT_USER,
      templateId: 'event',
      sourceIds: [],
      content: emptyDoc(),
      language: 'zh',
      length: 'brief',
      prompt: '',
      citations: [],
      relatedSources: [],
      versions: [version('v1', 'rpt-catl-event', '2026-09-08T15:10:00+08:00', 'manual', '已归档')],
    },
  ]
}

export const MOCK_METRICS = [
  { name: '营业收入（亿元）', current: '1,884.2', previous: '1,672.1', yoy: '+12.7%' },
  { name: '归母净利润（亿元）', current: '228.7', previous: '207.3', yoy: '+10.3%' },
  { name: '毛利率', current: '23.5%', previous: '25.1%', yoy: '-1.6pct' },
  { name: '经营活动现金流（亿元）', current: '356.8', previous: '298.1', yoy: '+19.7%' },
]
