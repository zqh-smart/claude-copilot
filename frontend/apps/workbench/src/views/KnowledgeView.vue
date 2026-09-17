<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, onUnmounted, ref, watch, watchEffect } from 'vue'
import { useRouter } from 'vue-router'

import {
  getKnowledgeGraph,
  listSegments,
  previewResearch,
  type DocumentSegment,
  type KnowledgeGraphSummary,
  type ResearchPreview,
} from '@/api/http'
import PageToolbar from '@/components/PageToolbar.vue'
import { clearChatLaunchContext, setChatLaunchContext } from '@/lib/chat-launch-context'
import { useWorkspaceStore } from '@/stores/workspace'

const router = useRouter()
const workspace = useWorkspaceStore()
const { documents } = storeToRefs(workspace)
const loading = ref(!workspace.loadedAt.documents)
const detailLoading = ref(false)
const testing = ref(false)
const error = ref('')
const query = ref('')
const segmentQuery = ref('')
const selectedId = ref('')
const tab = ref<'segments' | 'retrieve' | 'graph'>('segments')
const segments = ref<DocumentSegment[]>([])
const graph = ref<KnowledgeGraphSummary | null>(null)
const question = ref('2021年营业收入是多少？')
const preview = ref<ResearchPreview | null>(null)

const workbenchDocuments = computed(() => {
  const term = query.value.trim().toLocaleLowerCase()
  return documents.value.filter((item) => {
    const noise = /smoke|worker-soak|\.txt$|\.md$/i.test(item.filename)
    if (noise || (!item.segment_count && !item.metadata.company)) return false
    if (!term) return true
    return `${item.filename} ${item.metadata.company || ''} ${item.metadata.year || ''}`
      .toLocaleLowerCase()
      .includes(term)
  })
})

const selected = computed(
  () => documents.value.find((item) => item.doc_id === selectedId.value) || null,
)
const filteredSegments = computed(() => {
  const term = segmentQuery.value.trim().toLocaleLowerCase()
  if (!term) return segments.value
  return segments.value.filter((item) =>
    `${item.content} ${String(item.metadata?.section_type || '')}`
      .toLocaleLowerCase()
      .includes(term),
  )
})

function statusType(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  return 'warning'
}

async function loadDetail(docId: string) {
  detailLoading.value = true
  error.value = ''
  preview.value = null
  try {
    const [nextSegments, nextGraph] = await Promise.all([
      listSegments(docId),
      getKnowledgeGraph(docId).catch(() => null),
    ])
    if (selectedId.value === docId) {
      segments.value = nextSegments
      graph.value = nextGraph
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '文档详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

async function runPreview() {
  if (!selectedId.value || !question.value.trim()) return
  testing.value = true
  error.value = ''
  try {
    preview.value = await previewResearch(selectedId.value, question.value.trim())
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '检索测试失败'
  } finally {
    testing.value = false
  }
}

watch(selectedId, (docId) => {
  if (docId) void loadDetail(docId)
})

// Hand the document the user is inspecting to Agent Chat, together with the
// probe question they typed in the retrieval preview.
watchEffect(() => {
  setChatLaunchContext(
    selectedId.value
      ? {
          source: 'knowledge',
          resourceId: selectedId.value,
          prompt: question.value.trim() || undefined,
        }
      : undefined,
  )
})

onUnmounted(clearChatLaunchContext)

onMounted(async () => {
  try {
    await workspace.ensureDocuments()
    const first = documents.value.find(
      (item) => item.status === 'completed' && !/smoke|\.txt$/i.test(item.filename),
    )
    selectedId.value = first?.doc_id || documents.value[0]?.doc_id || ''
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '知识库加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="cc-page">
    <PageToolbar kicker="知识库" subtitle="浏览文档、切片和图谱，并验证实际召回。">
      <el-button @click="router.push('/research')">研究问答</el-button>
      <el-button type="primary" @click="router.push('/upload')">上传文档</el-button>
    </PageToolbar>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="knowledge-grid" v-loading="loading">
      <el-card shadow="never" class="document-panel">
        <el-input v-model="query" clearable placeholder="搜索公司、文件名或年份" class="cc-filter-input" />
        <div class="document-list">
          <button
            v-for="item in workbenchDocuments"
            :key="item.doc_id"
            class="document-row"
            :class="{ active: selectedId === item.doc_id }"
            @click="selectedId = item.doc_id"
          >
            <span class="file-badge">{{ item.filename.toLowerCase().endsWith('.pdf') ? 'PDF' : 'DOC' }}</span>
            <span class="document-copy">
              <strong>{{ item.metadata.company || item.filename }}</strong>
              <small>{{ item.metadata.year || '—' }} · {{ item.segment_count || 0 }} 切片</small>
            </span>
            <el-tag size="small" :type="statusType(item.status)">{{ item.status }}</el-tag>
          </button>
          <el-empty v-if="!workbenchDocuments.length" :image-size="60" description="没有匹配文档" />
        </div>
      </el-card>

      <el-card shadow="never" class="detail-panel" v-loading="detailLoading">
        <template #header>
          <div v-if="selected" class="document-header">
            <div><strong>{{ selected.metadata.company || selected.filename }}</strong><small>{{ selected.filename }}</small></div>
            <el-button text type="primary" @click="router.push(`/research?doc_id=${selected.doc_id}`)">研究问答</el-button>
          </div>
        </template>

        <el-tabs v-model="tab">
          <el-tab-pane label="文档切片" name="segments">
            <el-input v-model="segmentQuery" clearable placeholder="搜索切片内容" class="segment-search" />
            <div class="segment-list">
              <article v-for="item in filteredSegments.slice(0, 50)" :key="item.segment_id" class="segment-card">
                <header><b>#{{ item.position }}</b><span>{{ String(item.metadata?.section_type || 'section') }}</span></header>
                <p>{{ item.content }}</p>
              </article>
              <el-empty v-if="!filteredSegments.length" description="暂无切片" />
            </div>
          </el-tab-pane>

          <el-tab-pane label="召回测试" name="retrieve">
            <div class="retrieval-form">
              <el-input v-model="question" @keyup.enter="runPreview" />
              <el-button type="primary" :loading="testing" @click="runPreview">测试召回</el-button>
            </div>
            <div v-if="preview" class="retrieval-result">
              <el-descriptions :column="3" border>
                <el-descriptions-item label="意图">{{ preview.query_analysis?.intent || '—' }}</el-descriptions-item>
                <el-descriptions-item label="文本证据">{{ preview.hits?.length || 0 }}</el-descriptions-item>
                <el-descriptions-item label="结构化指标">{{ preview.metrics?.length || 0 }}</el-descriptions-item>
              </el-descriptions>
              <article v-for="hit in preview.hits || []" :key="hit.segment_id" class="segment-card">
                <header><b>{{ (hit.score * 100).toFixed(1) }}%</b><span>{{ hit.segment_id.slice(0, 16) }}</span></header>
                <p>{{ hit.content }}</p>
              </article>
            </div>
          </el-tab-pane>

          <el-tab-pane label="知识图谱" name="graph">
            <el-row :gutter="14">
              <el-col :span="12"><el-statistic title="节点" :value="graph?.nodes.length || 0" /></el-col>
              <el-col :span="12"><el-statistic title="关系" :value="graph?.relationships.length || 0" /></el-col>
            </el-row>
            <el-table :data="graph?.relationships.slice(0, 100) || []" height="470" class="graph-table">
              <el-table-column prop="relationship_type" label="关系" width="180" />
              <el-table-column prop="source_node_id" label="源节点" show-overflow-tooltip />
              <el-table-column prop="target_node_id" label="目标节点" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>
  </section>
</template>
