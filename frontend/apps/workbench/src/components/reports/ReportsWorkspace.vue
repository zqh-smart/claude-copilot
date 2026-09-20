<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { exportReportDraft } from '@/api/http'
import NewReportDialog from '@/components/reports/NewReportDialog.vue'
import ReportAIPanel from '@/components/reports/ReportAIPanel.vue'
import ReportEditor from '@/components/reports/ReportEditor.vue'
import ReportEditorHeader from '@/components/reports/ReportEditorHeader.vue'
import ReportSidebar from '@/components/reports/ReportSidebar.vue'
import ReportVersionDrawer from '@/components/reports/ReportVersionDrawer.vue'
import { clearChatLaunchContext, setChatLaunchContext } from '@/lib/chat-launch-context'
import { askReportAssistant, runReportAiCommand } from '@/services/reportAiService'
import { extractPlainText } from '@/services/reportDocument'
import { formatClock } from '@/services/reportFormat'
import { reportRepository } from '@/services/reportRepository'
import type {
  Citation,
  CreateReportInput,
  EditorJSON,
  EditorSelection,
  Report,
  ReportAiCommand,
  ReportListItem,
  ReportStatus,
  SaveState,
} from '@/types/report'

const CURRENT_USER = 'me'

const route = useRoute()
const router = useRouter()
const lists = ref<ReportListItem[]>([])
const report = ref<Report | null>(null)
const query = ref('')
const filter = ref<'all' | 'mine' | ReportStatus>('all')
const wizardOpen = ref(false)
const creatingReport = ref(false)
const historyOpen = ref(false)
const aiCollapsed = ref(window.innerWidth < 1366)
const tab = ref<'assistant' | 'citations' | 'data'>('assistant')
const selection = ref<EditorSelection | null>(null)
const activeCitationId = ref('')
const saveState = ref<SaveState>('idle')
const savedAt = ref('')
const pendingAi = ref(false)
const assistantDraft = ref('')
const messages = ref<Array<{ id: string; role: 'user' | 'assistant'; text: string }>>([])
const editorRef = ref<{
  replaceSelection: (text: string) => void
} | null>(null)

let saveTimer: number | undefined
const routeReportId = computed(() => {
  const value = route.params.draftId
  return typeof value === 'string' ? value : ''
})

const filteredLists = computed(() => {
  const term = query.value.trim().toLocaleLowerCase()
  return lists.value.filter((item) => {
    if (filter.value === 'mine' && item.createdBy !== CURRENT_USER) return false
    if (filter.value === 'draft' && item.status !== 'draft') return false
    if (filter.value === 'done' && item.status !== 'done') return false
    if (filter.value === 'archived' && item.status !== 'archived') return false
    if (!term) return true
    return `${item.title} ${item.company}`.toLocaleLowerCase().includes(term)
  })
})

async function refreshList() {
  lists.value = await reportRepository.listReports()
}

async function openReport(id: string, replace = false) {
  try {
    const next = await reportRepository.getReport(id)
    if (!next) return
    report.value = next
    reportRepository.setLastOpenedId(next.id)
    activeCitationId.value = next.citations[0]?.id || ''
    if (next.syncState === 'cached') {
      ElMessage.warning('后端暂不可用，当前显示最近一次同步缓存；恢复连接前不会覆盖后端草稿。')
    }
    const target = `/reports/${next.id}`
    if (route.path !== target) {
      await router[replace ? 'replace' : 'push'](target)
    }
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '报告加载失败')
  }
}

async function ensureActiveReport() {
  await refreshList()
  const requested = routeReportId.value
  if (requested) {
    await openReport(requested, true)
    return
  }
  const last = reportRepository.getLastOpenedId()
  const fallback = lists.value.find((item) => item.id === last)?.id || lists.value[0]?.id
  if (fallback) await openReport(fallback, true)
}

function scheduleSave(content: EditorJSON) {
  if (!report.value) return
  report.value = { ...report.value, content }
  const reportId = report.value.id
  const title = report.value.title
  window.clearTimeout(saveTimer)
  saveState.value = 'saving'
  saveTimer = window.setTimeout(async () => {
    try {
      const saved = await reportRepository.updateReport(
        reportId,
        { content, title },
        { type: 'autosave', description: '自动保存' },
      )
      if (report.value?.id === reportId) report.value = saved
      saveState.value = 'saved'
      savedAt.value = formatClock(saved.updatedAt)
      await refreshList()
    } catch (reason) {
      saveState.value = 'error'
      ElMessage.error(reason instanceof Error ? reason.message : '保存失败，修改尚未同步到后端')
    }
  }, 1400)
}

async function createReport(input: CreateReportInput) {
  creatingReport.value = true
  try {
    const created = await reportRepository.createReport(input)
    wizardOpen.value = false
    await refreshList()
    await openReport(created.id)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '报告框架生成失败')
  } finally {
    creatingReport.value = false
  }
}

async function completeReport() {
  if (!report.value) return
  report.value = await reportRepository.updateReport(report.value.id, { status: 'done' }, { type: 'manual', description: '定稿' })
  await refreshList()
  ElMessage.success('已标记完成')
}

async function shareReport() {
  await navigator.clipboard.writeText(window.location.href)
  ElMessage.success('报告链接已复制')
}

async function exportReport(format: 'html' | 'pdf' | 'md') {
  if (!report.value) return
  if (format === 'md') {
    const blob = new Blob([`# ${report.value.title}\n\n${extractPlainText(report.value.content)}`], {
      type: 'text/markdown',
    })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${report.value.title}.md`
    anchor.click()
    URL.revokeObjectURL(url)
    return
  }
  if (!report.value.backendDraftId || report.value.syncState === 'cached') {
    ElMessage.warning('HTML / PDF 导出需要连接后端并加载已同步草稿。')
    return
  }
  try {
    const artifact = await exportReportDraft(report.value.backendDraftId, format, report.value.title)
    const url = URL.createObjectURL(artifact.blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = artifact.filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '导出失败')
  }
}

async function handleCommand(command: ReportAiCommand) {
  tab.value = command === 'find_evidence' ? 'citations' : 'assistant'
  pendingAi.value = true
  try {
    const result = await runReportAiCommand({ command, selection: selection.value })
    messages.value.push({ id: `${Date.now()}`, role: 'assistant', text: result.message })
    if (result.replacement) editorRef.value?.replaceSelection(result.replacement)
    if (result.openCitations) tab.value = 'citations'
  } finally {
    pendingAi.value = false
  }
}

async function sendAssistant(text: string) {
  messages.value.push({ id: `${Date.now()}-u`, role: 'user', text })
  pendingAi.value = true
  try {
    const reply = await askReportAssistant(text, selection.value)
    messages.value.push({ id: `${Date.now()}-a`, role: 'assistant', text: reply })
  } finally {
    pendingAi.value = false
  }
}

function openCitation(item: Citation) {
  activeCitationId.value = item.id
  const url = `/api/fastapi/api/v1/documents/${encodeURIComponent(item.sourceId)}/source${item.page ? `#page=${item.page}` : ''}`
  window.open(url, '_blank', 'noreferrer')
}

function onCitationClick(id: string) {
  activeCitationId.value = id
  tab.value = 'citations'
  aiCollapsed.value = false
}

function publishChatContext() {
  setChatLaunchContext(
    report.value
      ? { source: 'reports', resourceId: report.value.backendDraftId || report.value.id }
      : undefined,
  )
}

watch(routeReportId, (id) => {
  if (id && id !== report.value?.id) void openReport(id, true)
})
watch(report, publishChatContext, { immediate: true })

onMounted(() => {
  void ensureActiveReport()
})
onUnmounted(() => {
  window.clearTimeout(saveTimer)
  clearChatLaunchContext()
})
onDeactivated(clearChatLaunchContext)
onActivated(() => {
  publishChatContext()
  void ensureActiveReport()
})
</script>

<template>
  <section class="reports-workspace">
    <ReportSidebar
      v-model:query="query"
      v-model:filter="filter"
      :reports="filteredLists"
      :active-id="report?.id || ''"
      @create="wizardOpen = true"
      @select="openReport"
    />

    <div class="reports-workspace__main">
      <template v-if="report">
        <ReportEditorHeader
          :report="report"
          :save-state="saveState"
          :saved-at="savedAt"
          :ai-collapsed="aiCollapsed"
          @share="shareReport"
          @history="historyOpen = true"
          @export="exportReport"
          @complete="completeReport"
          @toggle-ai="aiCollapsed = !aiCollapsed"
        />
        <ReportEditor
          :key="report.id"
          ref="editorRef"
          :content="report.content"
          @change="scheduleSave"
          @selection="selection = $event"
          @citation="onCitationClick"
          @command="handleCommand"
        />
      </template>
      <el-empty v-else description="还没有报告，点击左侧新建">
        <el-button type="primary" @click="wizardOpen = true">新建报告</el-button>
      </el-empty>
    </div>

    <ReportAIPanel
      v-if="!aiCollapsed && report"
      v-model:tab="tab"
      v-model:draft="assistantDraft"
      :selection="selection"
      :messages="messages"
      :pending="pendingAi"
      :citations="report.citations"
      :related="report.relatedSources"
      :active-citation-id="activeCitationId"
      @send="sendAssistant"
      @shortcut="sendAssistant"
      @open-citation="openCitation"
    />

    <NewReportDialog v-model="wizardOpen" :creating="creatingReport" @create="createReport" />
    <ReportVersionDrawer v-model="historyOpen" :versions="report?.versions || []" />
  </section>
</template>

<style scoped>
.reports-workspace {
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: #f7f9f8;
}
.reports-workspace__main {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}
</style>
