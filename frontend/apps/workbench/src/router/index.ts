import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import type { Component } from 'vue'

import AppLayout from '@/layout/AppLayout.vue'
import DashboardView from '@/views/DashboardView.vue'
import MigrationPlaceholderView from '@/views/MigrationPlaceholderView.vue'

const KnowledgeView = () => import('@/views/KnowledgeView.vue')
const EvalView = () => import('@/views/EvalView.vue')
const JobsView = () => import('@/views/JobsView.vue')
const UploadView = () => import('@/views/UploadView.vue')
const MetricsView = () => import('@/views/MetricsView.vue')
const CompareView = () => import('@/views/CompareView.vue')
const ResearchView = () => import('@/views/ResearchView.vue')
const ReportsView = () => import('@/views/ReportsView.vue')
const ChatMemoryView = () => import('@/views/ChatMemoryView.vue')
const AgentChatView = () => import('@/views/AgentChatView.vue')

type ViewLoader = () => Promise<Component>

const migratedViews: Record<string, ViewLoader> = {
  'agent-chat': AgentChatView,
  knowledge: KnowledgeView,
  research: ResearchView,
  compare: CompareView,
  metrics: MetricsView,
  eval: EvalView,
  jobs: JobsView,
  upload: UploadView,
  reports: ReportsView,
  'chat-memory': ChatMemoryView,
}

export function prefetchWorkspaceView(path: string) {
  const key = path.replace(/^\//, '')
  const loader = migratedViews[key]
  if (loader) void loader()
}

const workspaceRoutes = [
  ['agent-chat', '研究对话', '金融研究 Agent 对话'],
  ['knowledge', '知识库', '文档、切片与知识图谱管理'],
  ['chat-memory', '对话记忆', 'L0-L3 记忆浏览与检索'],
  ['research', '研究问答', '金融文档联合检索与研究'],
  ['compare', '对比分析', '公司、年度与指标对比'],
  ['reports', '报告中心', '报告创建、编辑、引用与导出'],
  ['metrics', '指标中心', '结构化财务指标与趋势'],
  ['eval', '评测中心', 'L2-L4 质量与回归门禁'],
  ['jobs', '任务中心', '文档处理任务与异常恢复'],
  ['upload', '文档上传', '上传并启动金融文档流水线'],
] as const

const children: RouteRecordRaw[] = [
  { path: '', name: 'dashboard', component: DashboardView, meta: { title: '工作台' } },
  // Compatibility aliases used by earlier links and acceptance checklists.
  // Keep the canonical paths in one place rather than rendering an empty
  // RouterView when an old bookmark is opened.
  { path: 'tasks', redirect: '/jobs' },
  { path: 'evaluation', redirect: '/eval' },
  ...workspaceRoutes.map(([path, title, description]) => ({
    path,
    name: path,
    component: migratedViews[path] || MigrationPlaceholderView,
    props: { title, description },
    meta: { title },
  })),
  {
    path: 'reports/:draftId',
    name: 'report-editor',
    component: ReportsView,
    meta: { title: '报告编辑' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/', component: AppLayout, children }],
})

router.onError((error, to) => {
  const isChunkLoadFail =
    /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(
      error.message,
    )
  if (!isChunkLoadFail) return
  const key = 'cc:chunk-reload'
  const last = Number(sessionStorage.getItem(key) || '0')
  const now = Date.now()
  if (now - last < 10_000) return
  sessionStorage.setItem(key, String(now))
  const target = to?.fullPath || '/'
  if (window.location.pathname + window.location.search + window.location.hash !== target) {
    window.location.assign(target)
  } else {
    window.location.reload()
  }
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || '工作台')} - Claude Copilot`
})

export default router
