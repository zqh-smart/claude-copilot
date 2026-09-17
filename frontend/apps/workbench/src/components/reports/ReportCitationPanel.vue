<script setup lang="ts">
import type { Citation, RelatedSource } from '@/types/report'

defineProps<{
  citations: Citation[]
  related: RelatedSource[]
  activeId: string
}>()

defineEmits<{
  open: [citation: Citation]
}>()
</script>

<template>
  <div class="citation-panel">
    <article
      v-for="(item, index) in citations"
      :key="item.id"
      class="citation-card"
      :class="{ 'is-active': item.id === activeId }"
    >
      <header>引用 {{ index + 1 }}</header>
      <strong>{{ item.sourceTitle }}</strong>
      <p>来源：{{ item.origin || '知识库' }}<template v-if="item.page"> · P{{ item.page }}</template></p>
      <p v-if="item.quote" class="citation-card__quote">{{ item.quote }}</p>
      <el-button text type="primary" @click="$emit('open', item)">查看原文</el-button>
    </article>
    <el-empty v-if="!citations.length" :image-size="56" description="正文还没有引用标记" />

    <div class="citation-panel__related">
      <div class="citation-panel__related-head">
        <strong>相关资料</strong>
        <span>更多</span>
      </div>
      <button v-for="item in related" :key="item.id" type="button" class="related-row">
        <b>{{ item.title }}</b>
        <small>来源：{{ item.origin }}<template v-if="item.page"> · P{{ item.page }}</template><template v-if="item.date"> · {{ item.date }}</template></small>
      </button>
    </div>
  </div>
</template>

<style scoped>
.citation-panel {
  display: flex;
  min-height: 0;
  height: 100%;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
}
.citation-card {
  padding: 10px 12px;
  border: 1px solid #e8ecea;
  border-radius: 12px;
  background: #fff;
}
.citation-card.is-active {
  border-color: var(--cc-brand-muted);
  background: #f4faf6;
}
.citation-card header {
  margin-bottom: 4px;
  color: var(--cc-brand-primary);
  font-size: 11px;
  font-weight: 700;
}
.citation-card strong {
  display: block;
  font-size: 13px;
  line-height: 1.4;
}
.citation-card p {
  margin: 4px 0 0;
  color: var(--cc-text-muted);
  font-size: 12px;
}
.citation-card__quote {
  color: var(--cc-text-secondary) !important;
  line-height: 1.55;
}
.citation-panel__related {
  margin-top: 8px;
}
.citation-panel__related-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  color: var(--cc-text-muted);
  font-size: 12px;
}
.related-row {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 3px;
  margin-bottom: 8px;
  padding: 8px 10px;
  border: 1px solid #eef2f0;
  border-radius: 10px;
  background: #fff;
  text-align: left;
  cursor: pointer;
}
.related-row b {
  font-size: 12px;
}
.related-row small {
  color: var(--cc-text-muted);
  font-size: 11px;
}
</style>
