import type { Component } from 'vue'
import {
  DataAnalysis,
  Document,
  Files,
  Histogram,
  HomeFilled,
  Memo,
  Operation,
  Search,
  Setting,
  UploadFilled,
} from '@element-plus/icons-vue'

export interface NavItem {
  path: string
  title: string
  icon: Component
  keywords?: string[]
}

export interface NavGroup {
  key: string
  title: string
  icon: Component
  items: NavItem[]
}

export const homeNavItem: NavItem = {
  path: '/',
  title: '工作台',
  icon: HomeFilled,
  keywords: ['home', 'dashboard', '首页', '总览'],
}

export const navGroups: NavGroup[] = [
  {
    key: 'nav-docs',
    title: '文档资产',
    icon: Files,
    items: [
      { path: '/knowledge', title: '知识库', icon: Files, keywords: ['文档', '切片', '图谱'] },
      { path: '/upload', title: '文档上传', icon: UploadFilled, keywords: ['ingest', '入库'] },
      { path: '/jobs', title: '任务中心', icon: Setting, keywords: ['流水线', '队列'] },
    ],
  },
  {
    key: 'nav-research',
    title: '研究产出',
    icon: Search,
    items: [
      { path: '/research', title: '研究问答', icon: Search, keywords: ['research', '检索'] },
      { path: '/compare', title: '对比分析', icon: DataAnalysis, keywords: ['公司', '年度'] },
      { path: '/reports', title: '报告中心', icon: Memo, keywords: ['草稿', '导出'] },
    ],
  },
  {
    key: 'nav-ops',
    title: '质量运营',
    icon: Operation,
    items: [
      { path: '/metrics', title: '指标中心', icon: Histogram, keywords: ['财务', '趋势'] },
      { path: '/eval', title: '评测中心', icon: Operation, keywords: ['L3', '门禁'] },
      { path: '/chat-memory', title: '对话记忆', icon: Document, keywords: ['memory', 'L0'] },
    ],
  },
]

export function groupKeyForPath(path: string): string | null {
  if (path.startsWith('/knowledge') || path.startsWith('/upload') || path.startsWith('/jobs')) {
    return 'nav-docs'
  }
  if (path.startsWith('/research') || path.startsWith('/compare') || path.startsWith('/reports')) {
    return 'nav-research'
  }
  if (path.startsWith('/metrics') || path.startsWith('/eval') || path.startsWith('/chat-memory')) {
    return 'nav-ops'
  }
  return null
}

export function flattenNavItems(): NavItem[] {
  return [homeNavItem, ...navGroups.flatMap((group) => group.items)]
}
