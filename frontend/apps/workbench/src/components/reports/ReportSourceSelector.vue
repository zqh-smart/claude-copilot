<script setup lang="ts">
import { computed, ref } from 'vue'

import type { DocumentSummary } from '@/api/http'

const props = defineProps<{
  documents: DocumentSummary[]
  selectedIds: string[]
}>()

const emit = defineEmits<{
  'update:selectedIds': [value: string[]]
}>()

const query = ref('')

const filtered = computed(() => {
  const term = query.value.trim().toLocaleLowerCase()
  return props.documents.filter((item) => {
    if (item.status !== 'completed' || !item.segment_count) return false
    if (/smoke|worker-soak|\.txt$/i.test(item.filename)) return false
    if (!term) return true
    return `${item.filename} ${item.metadata.company || ''} ${item.metadata.year || ''}`
      .toLocaleLowerCase()
      .includes(term)
  })
})

function toggle(id: string) {
  emit(
    'update:selectedIds',
    props.selectedIds.includes(id)
      ? props.selectedIds.filter((item) => item !== id)
      : [...props.selectedIds, id],
  )
}
</script>

<template>
  <div class="source-selector">
    <el-input v-model="query" clearable placeholder="搜索公司、文件名或年份" />
    <el-table :data="filtered" stripe max-height="280" size="small" class="source-selector__table">
      <el-table-column width="46">
        <template #default="scope">
          <el-checkbox :model-value="selectedIds.includes(scope.row.doc_id)" @change="toggle(scope.row.doc_id)" />
        </template>
      </el-table-column>
      <el-table-column prop="filename" label="研究材料" min-width="220" show-overflow-tooltip />
      <el-table-column label="公司" width="120" show-overflow-tooltip>
        <template #default="scope">{{ scope.row.metadata.company || '—' }}</template>
      </el-table-column>
      <el-table-column label="类型" width="90">
        <template #default="scope">{{ scope.row.metadata.doc_type || '—' }}</template>
      </el-table-column>
    </el-table>
    <p>已选择 {{ selectedIds.length }} 份材料。至少选择一份已完成解析的材料。</p>
  </div>
</template>

<style scoped>
.source-selector {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.source-selector p {
  margin: 0;
  color: var(--cc-text-muted);
  font-size: 12px;
}
</style>
