<script setup lang="ts">
import ReportAIAssistant from '@/components/reports/ReportAIAssistant.vue'
import ReportCitationPanel from '@/components/reports/ReportCitationPanel.vue'
import ReportDataPanel from '@/components/reports/ReportDataPanel.vue'
import type { Citation, EditorSelection, RelatedSource } from '@/types/report'

defineProps<{
  tab: 'assistant' | 'citations' | 'data'
  selection: EditorSelection | null
  messages: Array<{ id: string; role: 'user' | 'assistant'; text: string }>
  pending: boolean
  citations: Citation[]
  related: RelatedSource[]
  activeCitationId: string
}>()

const emit = defineEmits<{
  'update:tab': [value: 'assistant' | 'citations' | 'data']
  send: [text: string]
  shortcut: [text: string]
  openCitation: [citation: Citation]
}>()

const draft = defineModel<string>('draft', { default: '' })
</script>

<template>
  <aside class="report-ai-panel">
    <div class="report-ai-panel__tabs">
      <button type="button" :class="{ 'is-active': tab === 'assistant' }" @click="emit('update:tab', 'assistant')">AI研究助手</button>
      <button type="button" :class="{ 'is-active': tab === 'citations' }" @click="emit('update:tab', 'citations')">引用与来源</button>
      <button type="button" :class="{ 'is-active': tab === 'data' }" @click="emit('update:tab', 'data')">数据助手</button>
    </div>
    <div class="report-ai-panel__body">
      <ReportAIAssistant
        v-if="tab === 'assistant'"
        v-model:draft="draft"
        :selection="selection"
        :messages="messages"
        :pending="pending"
        @send="emit('send', $event)"
        @shortcut="emit('shortcut', $event)"
      />
      <ReportCitationPanel
        v-else-if="tab === 'citations'"
        :citations="citations"
        :related="related"
        :active-id="activeCitationId"
        @open="emit('openCitation', $event)"
      />
      <ReportDataPanel v-else />
    </div>
  </aside>
</template>

<style scoped>
.report-ai-panel {
  display: flex;
  width: 360px;
  flex-shrink: 0;
  flex-direction: column;
  min-height: 0;
  border-left: 1px solid #e8ecea;
  background: #fff;
}
.report-ai-panel__tabs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  padding: 10px 10px 0;
  border-bottom: 1px solid #e8ecea;
}
.report-ai-panel__tabs button {
  height: 36px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--cc-text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.report-ai-panel__tabs button.is-active {
  border-bottom-color: var(--cc-brand-primary);
  color: var(--cc-brand-primary);
  font-weight: 700;
}
.report-ai-panel__body {
  min-height: 0;
  flex: 1;
  padding: 14px 14px 16px;
  overflow: hidden;
}
</style>
