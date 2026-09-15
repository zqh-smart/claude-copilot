<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onActivated, onDeactivated, onUnmounted, ref } from 'vue'

import {
  cancelIngestionJob,
  getIngestionMetrics,
  listIngestionJobs,
  retryIngestionJob,
  type IngestionJob,
  type IngestionQueueMetrics,
} from '@/api/http'

const loading = ref(true)
const actingId = ref('')
const jobs = ref<IngestionJob[]>([])
const metrics = ref<IngestionQueueMetrics | null>(null)
const error = ref('')
let timer: number | undefined

const activeJobs = computed(
  () => jobs.value.filter((item) => ['ready', 'processing', 'retry_wait'].includes(item.status)).length,
)

function statusType(status: string) {
  if (['completed', 'succeeded'].includes(status)) return 'success'
  if (['failed', 'cancelled'].includes(status)) return 'danger'
  if (['processing', 'running'].includes(status)) return 'primary'
  return 'warning'
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

async function refresh(silent = false) {
  if (!silent) loading.value = true
  try {
    ;[jobs.value, metrics.value] = await Promise.all([
      listIngestionJobs(),
      getIngestionMetrics(),
    ])
    error.value = ''
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '任务队列加载失败'
  } finally {
    loading.value = false
  }
}

async function retry(job: IngestionJob) {
  actingId.value = job.job_id
  try {
    await retryIngestionJob(job.job_id)
    ElMessage.success('任务已重新入队')
    await refresh(true)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '重试失败')
  } finally {
    actingId.value = ''
  }
}

async function cancel(job: IngestionJob) {
  try {
    await ElMessageBox.confirm(`确认取消 ${job.filename}？`, '取消任务', { type: 'warning' })
  } catch {
    return
  }
  actingId.value = job.job_id
  try {
    await cancelIngestionJob(job.job_id)
    ElMessage.success('取消请求已提交')
    await refresh(true)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '取消失败')
  } finally {
    actingId.value = ''
  }
}

function startPolling() {
  if (timer) return
  void refresh()
  timer = window.setInterval(() => void refresh(true), 10_000)
}

function stopPolling() {
  window.clearInterval(timer)
  timer = undefined
}

onActivated(startPolling)
onDeactivated(stopPolling)
onUnmounted(stopPolling)
</script>

<template>
  <section class="page-stack" v-loading="loading">
    <div class="page-heading compact-heading">
      <div><p class="eyebrow">INGESTION OPERATIONS</p><h1>文档处理任务</h1><p>跟踪流水线阶段、重试失败任务并查看队列健康。</p></div>
      <el-space><el-button @click="refresh()">刷新</el-button><el-button type="primary" @click="$router.push('/upload')">上传文档</el-button></el-space>
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-alert
      v-for="alert in metrics?.alerts || []"
      :key="alert.code"
      :title="alert.message"
      :type="alert.severity === 'critical' ? 'error' : 'warning'"
      show-icon
      :closable="false"
    />

    <div class="metric-grid">
      <article class="metric-card"><span>任务总数</span><strong>{{ jobs.length }}</strong></article>
      <article class="metric-card"><span>活动任务</span><strong>{{ activeJobs }}</strong></article>
      <article class="metric-card"><span>工作进程</span><strong>{{ metrics?.active_worker_count || 0 }}</strong></article>
      <article class="metric-card" :class="{ danger: (metrics?.recent_failed_count || 0) > 0 }"><span>近期失败</span><strong>{{ metrics?.recent_failed_count || 0 }}</strong></article>
      <article class="metric-card"><span>队列状态</span><strong class="health-text">{{ metrics?.health_status || '—' }}</strong></article>
    </div>

    <el-card shadow="never">
      <template #header><div class="document-header"><strong>任务列表</strong><small>每 10 秒自动刷新</small></div></template>
      <el-table :data="jobs" stripe max-height="650">
        <el-table-column prop="filename" label="文件" min-width="260" show-overflow-tooltip />
        <el-table-column label="状态" width="120"><template #default="scope"><el-tag :type="statusType(scope.row.status)">{{ scope.row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="stage" label="阶段" width="130" />
        <el-table-column label="进度" width="180"><template #default="scope"><el-progress :percentage="scope.row.progress_percent" :stroke-width="8" /></template></el-table-column>
        <el-table-column label="尝试" width="90"><template #default="scope">{{ scope.row.attempt }}/{{ scope.row.max_attempts }}</template></el-table-column>
        <el-table-column label="更新时间" width="180"><template #default="scope">{{ formatDate(scope.row.updated_at) }}</template></el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="scope">
            <el-button v-if="scope.row.status === 'failed'" text type="primary" :loading="actingId === scope.row.job_id" @click="retry(scope.row)">重试</el-button>
            <el-button v-if="['ready', 'processing', 'retry_wait'].includes(scope.row.status)" text type="danger" :loading="actingId === scope.row.job_id" @click="cancel(scope.row)">取消</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>
