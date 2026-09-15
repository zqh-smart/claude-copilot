import { defineStore } from 'pinia'

import {
  listCompanies,
  listDocuments,
  listReportDrafts,
  listReportTemplates,
  listServingEvals,
  type CompanySummary,
  type DocumentSummary,
  type ReportDraftSummary,
  type ReportTemplate,
  type ServingEvalSummary,
} from '@/api/http'

const CACHE_TTL_MS = 60_000
const pending = new Map<string, Promise<unknown>>()

function dedupe<T>(key: string, loader: () => Promise<T>): Promise<T> {
  const active = pending.get(key) as Promise<T> | undefined
  if (active) return active
  const next = loader().finally(() => pending.delete(key))
  pending.set(key, next)
  return next
}

export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    documents: [] as DocumentSummary[],
    companies: [] as CompanySummary[],
    servingEvals: [] as ServingEvalSummary[],
    reportTemplates: [] as ReportTemplate[],
    reportDrafts: [] as ReportDraftSummary[],
    loadedAt: {
      documents: 0,
      companies: 0,
      servingEvals: 0,
      reportTemplates: 0,
      reportDrafts: 0,
    },
  }),
  actions: {
    isFresh(key: keyof typeof this.loadedAt) {
      return Date.now() - this.loadedAt[key] < CACHE_TTL_MS
    },
    async ensureDocuments(force = false) {
      if (!force && this.loadedAt.documents) {
        if (!this.isFresh('documents')) void this.refreshDocuments().catch(() => undefined)
        return this.documents
      }
      return this.refreshDocuments()
    },
    async refreshDocuments() {
      const items = await dedupe('documents', listDocuments)
      this.documents = items
      this.loadedAt.documents = Date.now()
      return items
    },
    async ensureCompanies(force = false) {
      if (!force && this.loadedAt.companies) {
        if (!this.isFresh('companies')) void this.refreshCompanies().catch(() => undefined)
        return this.companies
      }
      return this.refreshCompanies()
    },
    async refreshCompanies() {
      const items = await dedupe('companies', listCompanies)
      this.companies = items
      this.loadedAt.companies = Date.now()
      return items
    },
    async ensureServingEvals(force = false) {
      if (!force && this.loadedAt.servingEvals) {
        if (!this.isFresh('servingEvals')) void this.refreshServingEvals().catch(() => undefined)
        return this.servingEvals
      }
      return this.refreshServingEvals()
    },
    async refreshServingEvals() {
      const items = await dedupe('servingEvals', listServingEvals)
      this.servingEvals = items
      this.loadedAt.servingEvals = Date.now()
      return items
    },
    async ensureReportTemplates(force = false) {
      if (!force && this.loadedAt.reportTemplates) return this.reportTemplates
      const items = await dedupe('reportTemplates', listReportTemplates)
      this.reportTemplates = items
      this.loadedAt.reportTemplates = Date.now()
      return items
    },
    async ensureReportDrafts(force = false) {
      if (!force && this.loadedAt.reportDrafts) return this.reportDrafts
      const items = await dedupe('reportDrafts', listReportDrafts)
      this.reportDrafts = items
      this.loadedAt.reportDrafts = Date.now()
      return items
    },
    invalidateReports() {
      this.loadedAt.reportDrafts = 0
    },
  },
})
