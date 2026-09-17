<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const iframeSrc = computed(() => {
  const url = new URL(__CHAT_UI_URL__, window.location.origin)
  for (const key of ['cc_source', 'cc_resource', 'cc_prompt'] as const) {
    const value = route.query[key]
    if (typeof value === 'string' && value) url.searchParams.set(key, value)
  }
  return url.toString()
})
</script>

<template>
  <section class="cc-chat-page">
    <iframe
      :src="iframeSrc"
      title="Claude Copilot 研究对话"
      allow="clipboard-read; clipboard-write"
      class="chat-frame"
    />
  </section>
</template>

<style scoped>
.cc-chat-page {
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--cc-bg-card);
}

.chat-frame {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
  background: var(--cc-bg-card);
}
</style>
