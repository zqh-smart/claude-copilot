<script setup lang="ts">
import type { Editor } from '@tiptap/vue-3'

const props = defineProps<{
  editor: Editor | null
  tick?: number
}>()

function headingValue() {
  const editor = props.editor
  if (!editor) return 'p'
  if (editor.isActive('heading', { level: 1 })) return '1'
  if (editor.isActive('heading', { level: 2 })) return '2'
  if (editor.isActive('heading', { level: 3 })) return '3'
  return 'p'
}

function applyHeading(value: string) {
  const editor = props.editor
  if (!editor) return
  if (value === 'p') editor.chain().focus().setParagraph().run()
  else editor.chain().focus().toggleHeading({ level: Number(value) as 1 | 2 | 3 }).run()
}

function promptImage() {
  const src = window.prompt('图片 URL')?.trim()
  if (src) props.editor?.chain().focus().setImage({ src }).run()
}

function promptLink() {
  const href = window.prompt('链接 URL')?.trim()
  if (!href) {
    props.editor?.chain().focus().unsetLink().run()
    return
  }
  props.editor?.chain().focus().setLink({ href }).run()
}
</script>

<template>
  <div v-if="editor" class="report-toolbar">
    <select class="report-toolbar__select" :value="headingValue()" @change="applyHeading(($event.target as HTMLSelectElement).value)">
      <option value="p">正文</option>
      <option value="1">H1</option>
      <option value="2">H2</option>
      <option value="3">H3</option>
    </select>
    <button type="button" :class="{ 'is-active': editor.isActive('bold') }" @click="editor.chain().focus().toggleBold().run()">B</button>
    <button type="button" :class="{ 'is-active': editor.isActive('italic') }" @click="editor.chain().focus().toggleItalic().run()"><i>I</i></button>
    <button type="button" :class="{ 'is-active': editor.isActive('underline') }" @click="editor.chain().focus().toggleUnderline().run()"><u>U</u></button>
    <span class="report-toolbar__split" />
    <button type="button" :class="{ 'is-active': editor.isActive('bulletList') }" @click="editor.chain().focus().toggleBulletList().run()">• 列表</button>
    <button type="button" :class="{ 'is-active': editor.isActive('orderedList') }" @click="editor.chain().focus().toggleOrderedList().run()">1. 列表</button>
    <button type="button" :class="{ 'is-active': editor.isActive('blockquote') }" @click="editor.chain().focus().toggleBlockquote().run()">引用</button>
    <button type="button" @click="editor.chain().focus().setHorizontalRule().run()">分割线</button>
    <span class="report-toolbar__split" />
    <button type="button" @click="editor.chain().focus().insertTable({ rows: 3, cols: 4, withHeaderRow: true }).run()">表格</button>
    <button type="button" @click="promptImage">图片</button>
    <button type="button" @click="promptLink">链接</button>
    <span class="report-toolbar__split" />
    <button type="button" @click="editor.chain().focus().undo().run()">撤销</button>
    <button type="button" @click="editor.chain().focus().redo().run()">重做</button>
  </div>
</template>

<style scoped>
.report-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 8px 20px;
  border-bottom: 1px solid #e8ecea;
  background: #fff;
}
.report-toolbar button,
.report-toolbar__select {
  height: 30px;
  padding: 0 8px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--cc-text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.report-toolbar button:hover,
.report-toolbar__select:hover,
.report-toolbar button.is-active {
  background: var(--cc-bg-subtle);
  color: var(--cc-text-primary);
}
.report-toolbar__split {
  width: 1px;
  height: 16px;
  margin: 0 4px;
  background: #e8ecea;
}
</style>
