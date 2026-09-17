<script setup lang="ts">
import { NodeViewWrapper } from '@tiptap/vue-3'
import { emitCitationClick } from '@/components/reports/reportEditorEvents'

const props = defineProps<{
  node: { attrs: { citationId?: string; label?: string } }
  selected: boolean
}>()

const onCitationClick = (id: string) => emitCitationClick(id)

function handleClick(event: MouseEvent) {
  event.preventDefault()
  event.stopPropagation()
  if (props.node.attrs.citationId) onCitationClick(props.node.attrs.citationId)
}
</script>

<template>
  <node-view-wrapper as="sup" class="citation-mark" :class="{ 'is-selected': selected }">
    <button type="button" :title="`引用 ${node.attrs.label || ''}`" @click="handleClick">
      {{ node.attrs.label || '*' }}
    </button>
  </node-view-wrapper>
</template>

<style scoped>
.citation-mark {
  display: inline;
  margin: 0 1px;
}
.citation-mark button {
  padding: 0 2px;
  border: 0;
  background: transparent;
  color: var(--cc-brand-primary);
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
}
.citation-mark.is-selected button {
  border-radius: 4px;
  background: var(--cc-brand-soft);
}
</style>
