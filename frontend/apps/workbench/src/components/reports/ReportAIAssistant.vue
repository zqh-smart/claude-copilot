<script setup lang="ts">
import { Promotion } from '@element-plus/icons-vue'
import { computed } from 'vue'

import type { EditorSelection } from '@/types/report'

const props = defineProps<{
  selection: EditorSelection | null
  messages: Array<{ id: string; role: 'user' | 'assistant'; text: string }>
  pending: boolean
}>()

const emit = defineEmits<{
  send: [text: string]
  shortcut: [text: string]
}>()

const draft = defineModel<string>('draft', { default: '' })

const shortcuts = [
  '分析毛利率下降原因',
  '补充海外业务最新进展',
  '生成一张营收趋势图',
  '将这一节改成券商研报风格',
  '检查这段结论是否有证据支持',
]

const selectionLabel = computed(() => {
  const text = props.selection?.text.trim()
  if (!text) return ''
  return text.length > 36 ? `${text.slice(0, 36)}…` : text
})

function submit() {
  const text = draft.value.trim()
  if (!text || props.pending) return
  emit('send', text)
  draft.value = ''
}
</script>

<template>
  <div class="ai-assistant">
    <div class="ai-assistant__intro">
      <strong>你好，我是你的金融研究助手</strong>
      <p>可以帮你改写、扩展分析、补充数据、生成图表、查找证据或检查结论的依据。</p>
    </div>
    <p v-if="selectionLabel" class="ai-assistant__selection">已选中：{{ selectionLabel }}</p>
    <div class="ai-assistant__shortcuts">
      <button v-for="item in shortcuts" :key="item" type="button" @click="emit('shortcut', item)">{{ item }}</button>
    </div>
    <div class="ai-assistant__thread">
      <article v-for="item in messages" :key="item.id" :class="item.role">
        {{ item.text }}
      </article>
    </div>
    <div class="ai-assistant__composer">
      <el-input
        v-model="draft"
        type="textarea"
        :rows="3"
        resize="none"
        placeholder="请输入问题，或选择上方的建议..."
        @keydown.enter.exact.prevent="submit"
      />
      <el-button type="primary" circle :loading="pending" @click="submit">
        <el-icon><Promotion /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.ai-assistant {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  gap: 12px;
}
.ai-assistant__intro strong {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
}
.ai-assistant__intro p,
.ai-assistant__selection {
  margin: 0;
  color: var(--cc-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.ai-assistant__selection {
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--cc-brand-soft);
  color: var(--cc-brand-deep);
}
.ai-assistant__shortcuts {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ai-assistant__shortcuts button {
  padding: 8px 10px;
  border: 1px solid #e8ecea;
  border-radius: 10px;
  background: #fff;
  color: var(--cc-text-primary);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}
.ai-assistant__shortcuts button:hover {
  border-color: var(--cc-brand-muted);
  background: #f7faf8;
}
.ai-assistant__thread {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  overflow: auto;
}
.ai-assistant__thread article {
  padding: 8px 10px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}
.ai-assistant__thread .assistant {
  background: #f6f8f7;
}
.ai-assistant__thread .user {
  align-self: flex-end;
  background: var(--cc-brand-soft);
}
.ai-assistant__composer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: end;
}
</style>
