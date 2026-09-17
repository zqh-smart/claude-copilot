<script setup lang="ts">
import { formatReportTime } from '@/services/reportFormat'
import type { ReportVersion } from '@/types/report'

defineProps<{
  modelValue: boolean
  versions: ReportVersion[]
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
}>()
</script>

<template>
  <el-drawer :model-value="modelValue" title="版本历史" size="360px" @update:model-value="$emit('update:modelValue', Boolean($event))">
    <ol class="version-list">
      <li v-for="item in versions" :key="item.id">
        <b>{{ formatReportTime(item.createdAt) }}</b>
        <span>{{ item.description }}</span>
      </li>
    </ol>
    <p class="version-list__hint">完整版本恢复尚未接通后端。当前仅展示本地记录。</p>
  </el-drawer>
</template>

<style scoped>
.version-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.version-list li {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 0;
  border-bottom: 1px solid #eef2f0;
}
.version-list b {
  font-size: 13px;
}
.version-list span {
  color: var(--cc-text-secondary);
  font-size: 12px;
}
.version-list__hint {
  margin-top: 16px;
  color: var(--cc-text-muted);
  font-size: 12px;
}
</style>
