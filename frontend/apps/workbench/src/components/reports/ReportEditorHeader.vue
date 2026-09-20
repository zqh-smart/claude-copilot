<script setup lang="ts">
import { ArrowDown, Clock, Document, Fold, Share } from '@element-plus/icons-vue'

import { formatReportTime } from '@/services/reportFormat'
import { REPORT_STATUS_LABEL, REPORT_TYPE_LABEL, type Report, type SaveState } from '@/types/report'

defineProps<{
  report: Report
  saveState: SaveState
  savedAt: string
  aiCollapsed: boolean
}>()

const emit = defineEmits<{
  share: []
  history: []
  export: [format: 'html' | 'pdf' | 'md']
  complete: []
  toggleAi: []
}>()
</script>

<template>
  <header class="report-editor-header">
    <div class="report-editor-header__titles">
      <h2>{{ report.title }}</h2>
      <p>
        <span>{{ REPORT_TYPE_LABEL[report.type] }}</span>
        <span>创建于 {{ formatReportTime(report.createdAt) }}</span>
        <span>最后编辑：{{ formatReportTime(report.updatedAt) }}</span>
        <span v-if="saveState === 'saving'">保存中...</span>
        <span v-else-if="saveState === 'saved' && savedAt">已自动保存 {{ savedAt }}</span>
        <span v-else-if="saveState === 'error'" class="is-error">保存失败</span>
      </p>
    </div>
    <div class="report-editor-header__actions">
      <el-button @click="emit('share')">
        <el-icon><Share /></el-icon>
        分享
      </el-button>
      <el-button @click="emit('history')">
        <el-icon><Clock /></el-icon>
        版本历史
      </el-button>
      <el-dropdown trigger="click" @command="emit('export', $event)">
        <el-button>
          导出
          <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="html">导出 HTML</el-dropdown-item>
            <el-dropdown-item command="pdf">导出 PDF</el-dropdown-item>
            <el-dropdown-item command="md">导出 Markdown</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button type="primary" :disabled="report.status === 'done'" @click="emit('complete')">
        {{ report.status === 'done' ? '已完成' : '完成' }}
      </el-button>
      <el-button text @click="emit('toggleAi')">
        <el-icon><component :is="aiCollapsed ? Document : Fold" /></el-icon>
        {{ aiCollapsed ? '助手' : '' }}
      </el-button>
    </div>
  </header>
</template>

<style scoped>
.report-editor-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px 10px;
  border-bottom: 1px solid #e8ecea;
  background: #fff;
}
.report-editor-header__titles {
  min-width: 0;
}
.report-editor-header__titles h2 {
  margin: 0 0 6px;
  overflow: hidden;
  font-size: 18px;
  font-weight: 720;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.report-editor-header__titles p {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  margin: 0;
  color: var(--cc-text-muted);
  font-size: 12px;
}
.is-error {
  color: var(--cc-danger);
}
.report-editor-header__actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
}
</style>
