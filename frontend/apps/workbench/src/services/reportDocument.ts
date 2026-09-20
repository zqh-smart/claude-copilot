import type { ReportDraftSection } from '@/api/http'
import type { EditorJSON, EditorJSONNode } from '@/types/report'

export function textNode(text: string, marks?: EditorJSONNode['marks']): EditorJSONNode {
  return marks?.length ? { type: 'text', text, marks } : { type: 'text', text }
}

export function paragraph(text: string, extra: EditorJSONNode[] = []): EditorJSONNode {
  const content: EditorJSONNode[] = text ? [textNode(text), ...extra] : extra
  return { type: 'paragraph', content: content.length ? content : undefined }
}

export function heading(level: 1 | 2 | 3, text: string): EditorJSONNode {
  return { type: 'heading', attrs: { level }, content: [textNode(text)] }
}

export function citationNode(id: string, label: string): EditorJSONNode {
  return { type: 'citation', attrs: { citationId: id, label } }
}

function inlineContent(text: string): EditorJSONNode[] {
  const content: EditorJSONNode[] = []
  const pattern = /\[(C\d+)]/g
  let cursor = 0
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > cursor) content.push(textNode(text.slice(cursor, index)))
    content.push(citationNode(match[1], match[1].slice(1)))
    cursor = index + match[0].length
  }
  if (cursor < text.length) content.push(textNode(text.slice(cursor)))
  return content
}

function textBlocks(content: string): EditorJSONNode[] {
  const lines = content.split(/\r?\n/).filter((line) => line.trim())
  return lines.length
    ? lines.map((line) => ({ type: 'paragraph', content: inlineContent(line) }))
    : [paragraph('')]
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : []
}

export function draftSectionsToDocument(title: string, sections: ReportDraftSection[]): EditorJSON {
  return {
    type: 'doc',
    content: [
      heading(1, title),
      ...sections.map((section) => {
        const persisted = section.editor_json?.type === 'doc'
          ? (section.editor_json.content || []) as unknown as EditorJSONNode[]
          : textBlocks(section.content)
        return {
          type: 'reportSection',
          attrs: {
            sectionId: section.section_id,
            chapterId: section.chapter_id,
            citationIds: section.citation_ids,
            requiredMetrics: section.required_metrics,
            analysisRequirements: section.analysis_requirements,
          },
          content: [heading(2, section.title), ...persisted],
        }
      }),
    ],
  }
}

export function extractPlainText(node: EditorJSON | EditorJSONNode | undefined): string {
  if (!node) return ''
  if ('text' in node && node.text) return node.text
  if (node.type === 'citation') return `[${String(node.attrs?.citationId || '')}]`
  if (node.type === 'reportChart') return String(node.attrs?.title || '')
  if (node.type === 'aiInsight') return stringList(node.attrs?.items).join('；')
  const separator = ['doc', 'reportSection', 'bulletList', 'orderedList', 'listItem', 'table', 'tableRow'].includes(node.type)
    ? '\n'
    : ''
  return (node.content || []).map(extractPlainText).filter(Boolean).join(separator)
}

function collectCitationIds(node: EditorJSONNode): string[] {
  const own = node.type === 'citation' && node.attrs?.citationId
    ? [String(node.attrs.citationId)]
    : []
  return [...own, ...(node.content || []).flatMap(collectCitationIds)]
}

export function contentToSectionPayload(doc: EditorJSON): ReportDraftSection[] {
  const sectionNodes = (doc.content || []).filter((node) => node.type === 'reportSection')
  if (!sectionNodes.length) {
    throw new Error('报告章节结构无效，请刷新后重试')
  }
  return sectionNodes.map((node, index) => {
    const attrs = node.attrs || {}
    const children = node.content || []
    const titleIndex = children.findIndex((child) => child.type === 'heading')
    const titleNode = titleIndex >= 0 ? children[titleIndex] : undefined
    const body = titleIndex >= 0
      ? children.filter((_child, childIndex) => childIndex !== titleIndex)
      : children
    const citationIds = [
      ...stringList(attrs.citationIds),
      ...body.flatMap(collectCitationIds),
    ]
    return {
      section_id: String(attrs.sectionId || `section-${index + 1}`),
      chapter_id: String(attrs.chapterId || `chapter-${index + 1}`),
      title: extractPlainText(titleNode).trim() || `章节 ${index + 1}`,
      content: body.map(extractPlainText).filter(Boolean).join('\n').trim(),
      editor_json: { type: 'doc', content: body as unknown as Array<Record<string, unknown>> },
      citation_ids: [...new Set(citationIds)],
      required_metrics: stringList(attrs.requiredMetrics),
      analysis_requirements: stringList(attrs.analysisRequirements),
    }
  })
}
