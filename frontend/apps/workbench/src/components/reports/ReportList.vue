<script setup lang="ts">
import ReportListItem from '@/components/reports/ReportListItem.vue'
import type { ReportListItem as ReportListItemModel } from '@/types/report'

defineProps<{
  reports: ReportListItemModel[]
  activeId: string
}>()

defineEmits<{
  select: [id: string]
}>()
</script>

<template>
  <div class="report-list">
    <ReportListItem
      v-for="report in reports"
      :key="report.id"
      :report="report"
      :active="report.id === activeId"
      @select="$emit('select', report.id)"
    />
    <p v-if="!reports.length" class="report-list__empty">没有匹配的报告</p>
  </div>
</template>

<style scoped>
.report-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 8px 16px;
}
.report-list__empty {
  margin: 24px 8px;
  color: var(--cc-text-muted);
  font-size: 12px;
  text-align: center;
}
</style>
