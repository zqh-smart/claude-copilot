<script setup lang="ts">
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import { Table } from '@tiptap/extension-table'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import TableRow from '@tiptap/extension-table-row'
import Underline from '@tiptap/extension-underline'
import StarterKit from '@tiptap/starter-kit'
import { Editor, EditorContent, BubbleMenu } from '@tiptap/vue-3'
import { onBeforeUnmount, ref, watch } from 'vue'

import ReportEditorToolbar from '@/components/reports/ReportEditorToolbar.vue'
import { AIInsight, Citation, ReportChart, ReportSection } from '@/components/reports/tiptapExtensions'
import { setCitationClickHandler } from '@/components/reports/reportEditorEvents'
import type { EditorJSON, EditorSelection, ReportAiCommand } from '@/types/report'

const props = defineProps<{
  content: EditorJSON
}>()

const emit = defineEmits<{
  change: [content: EditorJSON]
  selection: [selection: EditorSelection | null]
  citation: [id: string]
  command: [command: ReportAiCommand]
}>()

setCitationClickHandler((id: string) => emit('citation', id))

type EditorLike = {
  state: { selection: { from: number; to: number }; doc: { textBetween: (from: number, to: number, sep: string) => string } }
  commands: { setContent: (content: EditorJSON, emitUpdate?: boolean) => boolean }
  chain: () => {
    focus: () => {
      insertContent: (value: unknown) => { run: () => void }
      insertContentAt: (range: { from: number; to: number }, value: string) => { run: () => void }
    }
  }
  getJSON: () => EditorJSON
  destroy: () => void
  isActive: (name: string, attrs?: Record<string, unknown>) => boolean
}

const editor = ref<EditorLike | null>(null)
const applyingRemote = ref(false)
const editorTick = ref(0)

function currentSelection(instance: EditorLike): EditorSelection | null {
  const { from, to } = instance.state.selection
  const text = instance.state.doc.textBetween(from, to, ' ')
  if (from === to || !text.trim()) return null
  return { from, to, text }
}

function createEditor() {
  editor.value?.destroy()
  editor.value = new Editor({
    content: props.content,
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
      Underline,
      Link.configure({ openOnClick: false, autolink: true }),
      Image,
      Placeholder.configure({ placeholder: '开始撰写研究报告...' }),
      Table.configure({ resizable: true }),
      TableRow,
      TableHeader,
      TableCell,
      ReportSection,
      AIInsight,
      ReportChart,
      Citation,
    ],
    editorProps: {
      attributes: { class: 'report-prose' },
    },
    onUpdate({ editor: instance }) {
      if (applyingRemote.value) return
      emit('change', instance.getJSON() as EditorJSON)
    },
    onTransaction() {
      editorTick.value += 1
    },
    onSelectionUpdate({ editor: instance }) {
      emit('selection', currentSelection(instance as unknown as EditorLike))
    },
  }) as unknown as EditorLike
}

createEditor()

watch(
  () => props.content,
  (next) => {
    const instance = editor.value
    if (!instance) return
    const current = JSON.stringify(instance.getJSON())
    if (current === JSON.stringify(next)) return
    applyingRemote.value = true
    instance.commands.setContent(next, false)
    applyingRemote.value = false
  },
)

onBeforeUnmount(() => {
  setCitationClickHandler(null)
  editor.value?.destroy()
})

function runCommand(command: ReportAiCommand) {
  emit('command', command)
}

function replaceSelection(text: string) {
  const instance = editor.value
  if (!instance) return
  const { from, to } = instance.state.selection
  instance.chain().focus().insertContentAt({ from, to }, text).run()
}

defineExpose({ replaceSelection, editor })
</script>

<template>
  <div class="report-editor">
    <ReportEditorToolbar :editor="(editor as never)" :tick="editorTick" />
    <div class="report-editor__scroll">
      <bubble-menu v-if="editor" :editor="(editor as never)" :tippy-options="{ duration: 100 }" class="report-bubble">
        <button type="button" @click="runCommand('find_evidence')">查看引用</button>
      </bubble-menu>
      <editor-content :editor="(editor as never)" class="report-editor__canvas" />
    </div>
  </div>
</template>

<style scoped>
.report-editor {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  background: #fff;
}
.report-editor__scroll {
  min-height: 0;
  overflow: auto;
}
.report-editor__canvas {
  max-width: 820px;
  min-height: calc(100vh - 280px);
  margin: 0 auto;
  padding: 28px 32px 80px;
}
.report-bubble {
  display: flex;
  gap: 2px;
  padding: 4px;
  border: 1px solid #e8ecea;
  border-radius: 10px;
  background: #fff;
  box-shadow: var(--cc-shadow-sm);
}
.report-bubble button {
  padding: 4px 8px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--cc-text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.report-bubble button:hover {
  background: var(--cc-brand-soft);
  color: var(--cc-brand-primary);
}
</style>

<style>
.report-prose {
  min-height: 60vh;
  outline: none;
  color: var(--cc-text-primary);
  font-size: 15px;
  line-height: 1.85;
}
.report-prose h1 {
  margin: 0 0 10px;
  font-size: 28px;
  line-height: 1.3;
}
.report-prose [data-type='report-section'] {
  display: flow-root;
}
.report-prose h2 {
  margin: 28px 0 10px;
  font-size: 18px;
}
.report-prose h3 {
  margin: 20px 0 8px;
  font-size: 15px;
}
.report-prose p {
  margin: 0 0 12px;
}
.report-prose blockquote {
  margin: 12px 0;
  padding: 4px 12px;
  border-left: 3px solid var(--cc-brand-muted);
  color: var(--cc-text-secondary);
}
.report-prose hr {
  margin: 24px 0;
  border: 0;
  border-top: 1px solid #e8ecea;
}
.report-prose table {
  width: 100%;
  margin: 12px 0 20px;
  border-collapse: collapse;
  font-size: 13px;
}
.report-prose th,
.report-prose td {
  padding: 8px 10px;
  border: 1px solid #e4ebe7;
  min-width: 64px;
  vertical-align: top;
}
.report-prose th {
  background: #f6faf7;
  font-weight: 650;
}
.report-prose img {
  max-width: 100%;
  border-radius: 8px;
}
.report-prose .selectedCell {
  background: #eef6f2;
}
.tiptap p.is-editor-empty:first-child::before {
  color: var(--cc-text-muted);
  content: attr(data-placeholder);
  float: left;
  height: 0;
  pointer-events: none;
}
</style>
