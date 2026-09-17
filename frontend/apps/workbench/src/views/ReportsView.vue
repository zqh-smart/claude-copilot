<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  assistReportDraft,
  createReportDraft,
  exportReportDraft,
  getReportDraft,
  patchReportDraft,
  type DraftStatus,
  type ReportCitation,
  type ReportDraft,
  type ReportDraftSection,
  type ReportLanguage,
  type ReportLength,
  type ReportTemplateId,
} from '@/api/http'
import PageToolbar from '@/components/PageToolbar.vue'
import { clearChatLaunchContext, setChatLaunchContext } from '@/lib/chat-launch-context'
import { useWorkspaceStore } from '@/stores/workspace'

const route = useRoute()
const router = useRouter()
const workspace = useWorkspaceStore()
const {
  documents,
  reportTemplates: templates,
  reportDrafts: drafts,
} = storeToRefs(workspace)
const loading = ref(
  !workspace.loadedAt.documents ||
    !workspace.loadedAt.reportTemplates ||
    !workspace.loadedAt.reportDrafts,
)
const busy = ref(false)
const error = ref('')
const selectedIds = ref<string[]>([])
const templateId = ref<ReportTemplateId>('comprehensive_financial')
const query = ref('')
const prompt = ref('')
const language = ref<ReportLanguage>('zh')
const length = ref<ReportLength>('standard')

const draft = ref<ReportDraft | null>(null)
const sectionId = ref('')
const content = ref('')
const title = ref('')
const dirty = ref(false)
const assistOpen = ref(false)
const assistInstruction = ref('润色本章，保持全部 [C#] 引用')
const assistSuggestion = ref('')

const filteredDocuments = computed(() => {
  const term = query.value.trim().toLocaleLowerCase()
  return documents.value.filter((item) => {
    if (item.status !== 'completed' || !item.segment_count) return false
    if (/smoke|worker-soak|\.txt$/i.test(item.filename)) return false
    if (!term) return true
    return `${item.filename} ${item.metadata.company || ''} ${item.metadata.year || ''}`
      .toLocaleLowerCase()
      .includes(term)
  })
})
const selectedTemplate = computed(
  () => templates.value.find((item) => item.template_id === templateId.value) || null,
)
const section = computed(
  () => draft.value?.sections.find((item) => item.section_id === sectionId.value) || null,
)
const citations = computed<ReportCitation[]>(() => {
  if (!draft.value || !section.value) return []
  const ids = new Set(section.value.citation_ids)
  return draft.value.citations.filter((item) => ids.has(item.citation_id))
})
const reportProgress = computed(() => {
  if (!draft.value?.sections.length) return 0
  const completed = draft.value.sections.filter(
    (item) => item.content.trim() && !item.content.includes('尚未检索到足够证据'),
  ).length
  return Math.round((completed / draft.value.sections.length) * 100)
})

function statusType(status: DraftStatus) {
  if (status === 'final') return 'success'
  if (status === 'revised') return 'warning'
  return 'info'
}

function toggleDocument(docId: string) {
  selectedIds.value = selectedIds.value.includes(docId)
    ? selectedIds.value.filter((item) => item !== docId)
    : [...selectedIds.value, docId]
}

function updateLocalSection(nextContent = content.value) {
  if (!draft.value || !section.value) return
  draft.value = {
    ...draft.value,
    sections: draft.value.sections.map((item) =>
      item.section_id === section.value?.section_id ? { ...item, content: nextContent } : item,
    ),
  }
}

function selectSection(next: ReportDraftSection) {
  if (dirty.value) updateLocalSection()
  sectionId.value = next.section_id
  content.value = next.content
  dirty.value = false
  assistSuggestion.value = ''
}

function hydrateDraft(next: ReportDraft) {
  draft.value = next
  title.value = next.title
  const preferred = next.sections.find((item) => item.section_id === sectionId.value)
  const first = preferred || next.sections[0]
  sectionId.value = first?.section_id || ''
  content.value = first?.content || ''
  dirty.value = false
}

async function loadDraft(draftId: string) {
  loading.value = true
  error.value = ''
  try {
    hydrateDraft(await getReportDraft(draftId))
  } catch (reason) {
    draft.value = null
    error.value = reason instanceof Error ? reason.message : '报告草稿加载失败'
  } finally {
    loading.value = false
  }
}

async function generateDraft() {
  if (!selectedIds.value.length || !selectedTemplate.value) return
  busy.value = true
  error.value = ''
  try {
    const next = await createReportDraft({
      doc_ids: selectedIds.value,
      template_id: selectedTemplate.value.template_id,
      prompt: prompt.value.trim(),
      language: language.value,
      length: length.value,
      top_k: 6,
    })
    hydrateDraft(next)
    await router.push(`/reports/${next.draft_id}`)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '报告草稿生成失败'
  } finally {
    busy.value = false
  }
}

async function saveCurrent() {
  if (!draft.value) return false
  updateLocalSection()
  busy.value = true
  error.value = ''
  try {
    const updated = await patchReportDraft(draft.value.draft_id, {
      title: title.value.trim() || draft.value.title,
      sections: draft.value.sections,
    })
    hydrateDraft(updated)
    return true
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '报告保存失败'
    return false
  } finally {
    busy.value = false
  }
}

async function setFinal() {
  if (!draft.value) return
  if (dirty.value && !(await saveCurrent())) return
  busy.value = true
  try {
    hydrateDraft(await patchReportDraft(draft.value.draft_id, { status: 'final' }))
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '定稿失败'
  } finally {
    busy.value = false
  }
}

async function runAssist(apply: boolean) {
  if (!draft.value || !section.value || !assistInstruction.value.trim()) return
  if (dirty.value && !(await saveCurrent())) return
  busy.value = true
  error.value = ''
  try {
    const response = await assistReportDraft(draft.value.draft_id, {
      section_id: section.value.section_id,
      instruction: assistInstruction.value.trim(),
      apply,
    })
    assistSuggestion.value = response.suggested_content
    if (response.applied && response.draft) hydrateDraft(response.draft)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '报告助手执行失败'
  } finally {
    busy.value = false
  }
}

function useSuggestion() {
  content.value = assistSuggestion.value
  dirty.value = true
  assistOpen.value = false
}

async function download(format: 'html' | 'pdf') {
  if (!draft.value) return
  if (dirty.value && !(await saveCurrent())) return
  busy.value = true
  error.value = ''
  try {
    const artifact = await exportReportDraft(draft.value.draft_id, format, title.value)
    const url = URL.createObjectURL(artifact.blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = artifact.filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '报告导出失败'
  } finally {
    busy.value = false
  }
}

function sourceUrl(item: ReportCitation) {
  return `/api/fastapi/api/v1/documents/${encodeURIComponent(item.doc_id)}/source${item.page ? `#page=${item.page}` : ''}`
}

onMounted(async () => {
  try {
    await Promise.all([
      workspace.ensureDocuments(),
      workspace.ensureReportTemplates(),
      workspace.ensureReportDrafts(),
    ])
    templateId.value = templates.value[0]?.template_id || 'comprehensive_financial'
    const firstDocument = filteredDocuments.value[0]
    if (firstDocument) selectedIds.value = [firstDocument.doc_id]
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '报告中心加载失败'
  } finally {
    loading.value = false
  }
})

watch(
  () => route.params.draftId,
  (value) => {
    if (typeof value === 'string' && value) void loadDraft(value)
    else draft.value = null
  },
  { immediate: true },
)

/**
 * Hand the report's material selection to Agent Chat.
 *
 * `cc_resource` is a single opaque id, so only the first selected document is
 * handed off — the contract has no room for a document list. An open draft wins,
 * since that is the most specific thing the user is looking at.
 */
function publishChatContext() {
  const resourceId = draft.value?.draft_id || selectedIds.value[0]
  setChatLaunchContext(
    resourceId
      ? {
          source: 'reports',
          resourceId,
          prompt: prompt.value.trim() || undefined,
        }
      : undefined,
  )
}

watchEffect(publishChatContext)

onUnmounted(clearChatLaunchContext)

// SPA navigation in <KeepAlive> never fires `onUnmounted`; clear here so the
// top-bar handoff does not leak the previous draft / document into unrelated
// tabs (e.g. /upload, /jobs, /metrics).
onDeactivated(clearChatLaunchContext)
onActivated(publishChatContext)
</script>

<template>
  <section class="cc-page" v-loading="loading">
    <template v-if="!draft">
      <PageToolbar kicker="报告中心" subtitle="按模板组织真实文档证据，生成可编辑、可引用、可导出的金融报告。">
        <el-tag effect="plain">{{ drafts.length }} 份草稿</el-tag>
      </PageToolbar>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

      <el-steps :active="0" finish-status="success" simple>
        <el-step title="选择材料与模板" /><el-step title="生成报告初稿" /><el-step title="人工与 AI 调整" /><el-step title="定稿导出" />
      </el-steps>

      <el-card v-if="drafts.length" shadow="never">
        <template #header><strong>已有报告</strong></template>
        <el-table :data="drafts" stripe max-height="250">
          <el-table-column prop="title" label="标题" min-width="320" show-overflow-tooltip />
          <el-table-column prop="template_id" label="模板" width="210" />
          <el-table-column label="状态" width="100"><template #default="scope"><el-tag :type="statusType(scope.row.status)">{{ scope.row.status }}</el-tag></template></el-table-column>
          <el-table-column prop="source_count" label="材料" width="80" />
          <el-table-column prop="updated_at" label="更新时间" width="190" />
          <el-table-column width="110"><template #default="scope"><el-button text type="primary" @click="router.push(`/reports/${scope.row.draft_id}`)">继续编辑</el-button></template></el-table-column>
        </el-table>
      </el-card>

      <div class="report-create-grid">
        <div class="page-stack">
          <el-card shadow="never">
            <template #header><strong>1. 选择知识库文件</strong></template>
            <el-input v-model="query" clearable placeholder="搜索公司、文件名或年份" class="report-search" />
            <el-table :data="filteredDocuments" stripe max-height="390">
              <el-table-column width="54"><template #default="scope"><el-checkbox :model-value="selectedIds.includes(scope.row.doc_id)" @change="toggleDocument(scope.row.doc_id)" /></template></el-table-column>
              <el-table-column prop="filename" label="文件" min-width="300" show-overflow-tooltip />
              <el-table-column label="公司" width="190" show-overflow-tooltip><template #default="scope">{{ scope.row.metadata.company || '—' }}</template></el-table-column>
              <el-table-column label="年度" width="90"><template #default="scope">{{ scope.row.metadata.year || '—' }}</template></el-table-column>
              <el-table-column prop="segment_count" label="切片" width="80" />
              <template #empty>
                <el-empty
                  :description="query ? '没有匹配的可用文档' : '暂无已完成解析的报告材料'"
                >
                  <el-button v-if="query" @click="query = ''">清除搜索</el-button>
                  <el-button v-else type="primary" @click="router.push('/upload')">上传报告材料</el-button>
                </el-empty>
              </template>
            </el-table>
            <p class="selection-summary">已选择 {{ selectedIds.length }} 份材料</p>
          </el-card>

          <el-card shadow="never">
            <template #header><strong>2. 选择专业模板</strong></template>
            <div class="template-grid">
              <button v-for="item in templates" :key="item.template_id" class="template-card" :class="{ active: item.template_id === templateId }" @click="templateId = item.template_id">
                <span>{{ item.category }}</span><b>{{ item.name }}</b><small>{{ item.description }}</small><em>{{ item.chapters.length }} 个章节</em>
              </button>
            </div>
          </el-card>
        </div>

        <el-card shadow="never" class="report-parameter-card">
          <template #header><strong>3. 生成参数</strong></template>
          <el-form label-position="top">
            <el-form-item label="重点要求"><el-input v-model="prompt" type="textarea" :rows="5" maxlength="2000" show-word-limit placeholder="例如：重点分析盈利质量、现金流和主要风险。" /></el-form-item>
            <el-form-item label="语言"><el-radio-group v-model="language"><el-radio-button value="zh">中文</el-radio-button><el-radio-button value="en">English</el-radio-button></el-radio-group></el-form-item>
            <el-form-item label="篇幅"><el-radio-group v-model="length"><el-radio-button value="brief">精简</el-radio-button><el-radio-button value="standard">标准</el-radio-button><el-radio-button value="long">详细</el-radio-button></el-radio-group></el-form-item>
            <el-alert title="报告只使用所选材料；缺少证据的章节将明确标记，不自动编造。" type="info" :closable="false" show-icon />
            <el-button class="generate-report" type="primary" :loading="busy" :disabled="!selectedIds.length" @click="generateDraft">生成报告初稿</el-button>
          </el-form>
        </el-card>
      </div>
    </template>

    <template v-else>
      <div class="report-editor-heading">
        <div><el-button text type="primary" @click="router.push('/reports')">← 返回报告中心</el-button><el-input v-model="title" class="report-title-input" @input="dirty = true" /><p>{{ draft.sources.length }} 份材料 · {{ draft.sections.length }} 章 · {{ draft.status }}<span v-if="dirty"> · 有未保存修改</span></p></div>
        <div class="report-actions"><el-button :loading="busy" @click="saveCurrent">保存</el-button><el-button @click="download('html')">导出 HTML</el-button><el-button @click="download('pdf')">导出 PDF</el-button><el-button type="warning" plain @click="assistOpen = true">AI 助改</el-button><el-button type="primary" @click="setFinal">标记定稿</el-button></div>
      </div>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <el-alert v-for="warning in draft.warnings" :key="warning" :title="warning" type="warning" show-icon :closable="false" />

      <div class="report-editor-grid">
        <el-card shadow="never" class="chapter-nav">
          <el-progress :percentage="reportProgress" :stroke-width="8" />
          <button v-for="(item, index) in draft.sections" :key="item.section_id" :class="{ active: item.section_id === sectionId }" @click="selectSection(item)"><span>{{ String(index + 1).padStart(2, '0') }}</span>{{ item.title }}</button>
        </el-card>
        <el-card shadow="never" class="chapter-editor">
          <template #header><div class="card-title"><strong>{{ section?.title }}</strong><el-tag :type="citations.length ? 'success' : 'warning'">{{ citations.length }} 条引用</el-tag></div></template>
          <div v-if="section?.analysis_requirements.length" class="requirement-box"><b>分析要求</b><span v-for="item in section.analysis_requirements" :key="item">· {{ item }}</span></div>
          <p v-if="section?.required_metrics.length" class="required-metrics">必需指标：{{ section.required_metrics.join('、') }}</p>
          <el-input v-model="content" type="textarea" :rows="18" resize="vertical" @input="dirty = true" />
          <h3 class="section-title">引用路径</h3>
          <div class="citation-list">
            <a v-for="item in citations" :key="item.citation_id" :href="sourceUrl(item)" target="_blank" rel="noreferrer"><b>[{{ item.citation_id }}] {{ item.path_label }}</b><span>{{ item.excerpt }}</span></a>
            <el-empty v-if="!citations.length" :image-size="55" description="本章暂无引用" />
          </div>
        </el-card>
      </div>

      <el-drawer v-model="assistOpen" title="报告 AI 助手" size="440px">
        <p class="assist-section">当前章节：{{ section?.title || '—' }}</p>
        <el-input v-model="assistInstruction" type="textarea" :rows="4" />
        <div class="assist-actions"><el-button :loading="busy" @click="runAssist(false)">生成建议</el-button><el-button type="primary" :loading="busy" @click="runAssist(true)">直接改本章</el-button></div>
        <div v-if="assistSuggestion" class="assist-preview"><b>建议稿</b><pre>{{ assistSuggestion }}</pre><el-button type="primary" plain @click="useSuggestion">写入编辑框</el-button></div>
      </el-drawer>
    </template>
  </section>
</template>
