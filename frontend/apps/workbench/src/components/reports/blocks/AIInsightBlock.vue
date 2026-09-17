<script setup lang="ts">
import { NodeViewWrapper } from '@tiptap/vue-3'
import { computed } from 'vue'

const props = defineProps<{
  node: { attrs: { items?: string[] } }
  selected: boolean
}>()

const items = computed(() => (Array.isArray(props.node.attrs.items) ? props.node.attrs.items : []))
</script>

<template>
  <node-view-wrapper
    class="ai-insight-block"
    :class="{ 'is-selected': selected }"
    data-type="ai-insight"
  >
    <div class="ai-insight-block__badge">AI 总结</div>
    <ul>
      <li v-for="item in items" :key="item">{{ item }}</li>
    </ul>
  </node-view-wrapper>
</template>

<style scoped>
.ai-insight-block {
  margin: 18px 0;
  padding: 14px 16px 12px;
  border: 1px solid #e4eee8;
  border-radius: 12px;
  background: #f6faf7;
}
.ai-insight-block.is-selected {
  border-color: var(--cc-brand-muted);
  box-shadow: 0 0 0 3px rgb(26 89 69 / 8%);
}
.ai-insight-block__badge {
  margin-bottom: 8px;
  color: var(--cc-brand-primary);
  font-size: 12px;
  font-weight: 700;
}
.ai-insight-block ul {
  margin: 0;
  padding-left: 18px;
  color: var(--cc-text-primary);
  font-size: 14px;
  line-height: 1.7;
}
</style>
