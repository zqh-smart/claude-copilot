<script setup lang="ts">
import { PRODUCT_TEMPLATES, type ReportType } from '@/types/report'

defineProps<{
  modelValue: ReportType
}>()

defineEmits<{
  'update:modelValue': [value: ReportType]
}>()
</script>

<template>
  <div class="template-selector">
    <button
      v-for="item in PRODUCT_TEMPLATES"
      :key="item.id"
      type="button"
      class="template-selector__card"
      :class="{ 'is-active': modelValue === item.id }"
      @click="$emit('update:modelValue', item.id)"
    >
      <b>{{ item.name }}</b>
      <span>{{ item.description }}</span>
    </button>
  </div>
</template>

<style scoped>
.template-selector {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.template-selector__card {
  display: flex;
  min-height: 92px;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  border: 1px solid #e4ebe7;
  border-radius: 12px;
  background: #fff;
  text-align: left;
  cursor: pointer;
}
.template-selector__card.is-active,
.template-selector__card:hover {
  border-color: var(--cc-brand-muted);
  background: #f4faf7;
}
.template-selector__card b {
  font-size: 14px;
}
.template-selector__card span {
  color: var(--cc-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}
</style>
