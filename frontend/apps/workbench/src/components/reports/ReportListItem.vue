<script setup lang="ts">
import { formatReportTime } from '@/services/reportFormat'
import { REPORT_TYPE_LABEL, type ReportListItem } from '@/types/report'

defineProps<{
  report: ReportListItem
  active: boolean
}>()

defineEmits<{
  select: []
}>()
</script>

<template>
  <button type="button" class="report-list-item" :class="{ 'is-active': active }" @click="$emit('select')">
    <span class="report-list-item__title">{{ report.title }}</span>
    <span class="report-list-item__meta">{{ REPORT_TYPE_LABEL[report.type] }}</span>
    <span class="report-list-item__time">{{ formatReportTime(report.updatedAt) }}</span>
  </button>
</template>

<style scoped>
.report-list-item {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 10px 12px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.report-list-item:hover {
  background: var(--cc-bg-hover);
}
.report-list-item.is-active {
  background: var(--cc-brand-soft);
}
.report-list-item__title {
  color: var(--cc-text-primary);
  font-size: 13px;
  font-weight: 650;
  line-height: 1.4;
}
.report-list-item.is-active .report-list-item__title {
  color: var(--cc-brand-deep);
}
.report-list-item__meta,
.report-list-item__time {
  color: var(--cc-text-muted);
  font-size: 11px;
}
</style>
