<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onActivated, onDeactivated, onUnmounted, ref } from 'vue'

import PageToolbar from '@/components/PageToolbar.vue'
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
  <section class="cc-page" v-loading="loading">
    <PageToolbar kicker="任务中心" subtitle="跟踪流水线阶段、重试失败任务并查看队列健康。">
      <el-button @click="refresh()">刷新</el-button>
      <el-button type="primary" @click="$router.push('/upload')">上传文档</el-button>
    </PageToolbar>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-alert
      v-for="alert in metrics?.alerts || []"
      :key="alert.code"
      :title="alert.message"
      :type="alert.severity === 'critical' ? 'error' : 'warning'"
      show-icon
      :closable="false"
    />

    <div class="overview-kpis">
      <article class="overview-kpi overview-kpi--static">
        <div class="overview-kpi__head"><span>任务总数</span></div>
        <div class="overview-kpi__value">{{ jobs.length }}</div>
        <p class="overview-kpi__meta">当前队列全部任务</p>
      </article>
      <article class="overview-kpi overview-kpi--static overview-kpi--warning">
        <div class="overview-kpi__head"><span>活动任务</span></div>
        <div class="overview-kpi__value">{{ activeJobs }}</div>
        <p class="overview-kpi__meta">ready / processing / retry_wait</p>
      </article>
      <article class="overview-kpi overview-kpi--static">
        <div class="overview-kpi__head"><span>工作进程</span></div>
        <div class="overview-kpi__value">{{ metrics?.active_worker_count || 0 }}</div>
        <p class="overview-kpi__meta">正在消费队列的 worker</p>
      </article>
      <article class="overview-kpi overview-kpi--static" :class="{ 'overview-kpi--danger': (metrics?.recent_failed_count || 0) > 0 }">
        <div class="overview-kpi__head"><span>近期失败</span></div>
        <div class="overview-kpi__value">{{ metrics?.recent_failed_count || 0 }}</div>
        <p class="overview-kpi__meta">队列状态 {{ metrics?.health_status || '—' }}</p>
      </article>
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
