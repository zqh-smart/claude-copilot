<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'

import ReportList from '@/components/reports/ReportList.vue'
import type { ReportListItem, ReportStatus } from '@/types/report'

const props = defineProps<{
  query: string
  filter: 'all' | 'mine' | ReportStatus
  reports: ReportListItem[]
  activeId: string
}>()

const emit = defineEmits<{
  'update:query': [value: string]
  'update:filter': [value: typeof props.filter]
  create: []
  select: [id: string]
}>()

const filters: Array<{ id: typeof props.filter; label: string }> = [
  { id: 'all', label: '全部' },
  { id: 'mine', label: '我的' },
  { id: 'draft', label: '草稿' },
  { id: 'done', label: '已完成' },
  { id: 'archived', label: '已归档' },
]
</script>

<template>
  <aside class="report-sidebar">
    <div class="report-sidebar__head">
      <el-input
        :model-value="query"
        clearable
        placeholder="搜索报告..."
        @update:model-value="emit('update:query', String($event || ''))"
      />
      <el-button type="primary" class="report-sidebar__create" @click="emit('create')">
        <el-icon><Plus /></el-icon>
        新建报告
      </el-button>
      <div class="report-sidebar__filters">
        <button
          v-for="item in filters"
          :key="item.id"
          type="button"
          :class="{ 'is-active': filter === item.id }"
          @click="emit('update:filter', item.id)"
        >
          {{ item.label }}
        </button>
      </div>
    </div>
    <div class="report-sidebar__list">
      <ReportList :reports="reports" :active-id="activeId" @select="emit('select', $event)" />
    </div>
  </aside>
</template>

<style scoped>
.report-sidebar {
  display: flex;
  width: 262px;
  flex-shrink: 0;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid #e8ecea;
  background: #fbfcfc;
}
.report-sidebar__head {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 12px 8px;
}
.report-sidebar__create {
  width: 100%;
}
.report-sidebar__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.report-sidebar__filters button {
  padding: 4px 8px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--cc-text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.report-sidebar__filters button.is-active {
  background: var(--cc-brand-soft);
  color: var(--cc-brand-primary);
  font-weight: 650;
}
.report-sidebar__list {
  min-height: 0;
  overflow: auto;
}
</style>
