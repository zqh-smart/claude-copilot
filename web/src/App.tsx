import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { api } from "./api";
import type {
  CompanySummary,
  CompareResponse,
  DocumentRecord,
  IngestionJob,
  IngestionQueueMetrics,
  MetricObservation,
  MetricTrend,
  PortfolioDashboard,
  ReportOutlineResponse,
  ResearchResponse,
  ScorecardSummary,
  ServingEvalSummary,
} from "./api";
import "./index.css";

type Tab = "research" | "compare" | "reports" | "metrics" | "eval" | "jobs" | "upload";

const SUGGESTED_QUESTIONS = [
  "2021年营业收入是多少？",
  "管理层如何讨论与分析公司经营情况？",
  "公司面临哪些市场风险或风险暴露？",
];

function statusChip(status: string) {
  if (status === "completed" || status === "succeeded") return "chip good";
  if (status === "failed") return "chip bad";
  return "chip warn";
}

function formatValue(value: number | string | null | undefined) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return value.toLocaleString("zh-CN");
  return String(value);
}

const ROUTE_LABELS: Record<string, string> = {
  vector: "语义",
  sql: "结构化",
  graph: "图谱",
};

const INTENT_LABELS: Record<string, string> = {
  semantic: "语义检索",
  structured: "结构化查询",
  relational: "关系查询",
  hybrid: "混合检索",
};

function formatFusionRoute(route: string) {
  return ROUTE_LABELS[route] ?? route;
}

function formatFusionIntent(intent: string) {
  return INTENT_LABELS[intent] ?? intent;
}

function downloadMarkdown(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function TrendChart({ trend }: { trend: MetricTrend }) {
  if (trend.points.length < 2) return <p className="muted">至少需要两个年度数据点才能绘制趋势。</p>;
  const values = trend.points.map((point) => point.value);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const points = trend.points
    .map((point, index) => {
      const x = 24 + (index * 552) / Math.max(trend.points.length - 1, 1);
      const y = 168 - ((point.value - minimum) / range) * 132;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <div className="trend-chart">
      <svg viewBox="0 0 600 200" role="img" aria-label={`${trend.metric_key} 年度趋势`}>
        <polyline points={points} fill="none" stroke="currentColor" strokeWidth="4" />
        {trend.points.map((point, index) => {
          const x = 24 + (index * 552) / Math.max(trend.points.length - 1, 1);
          const y = 168 - ((point.value - minimum) / range) * 132;
          return <circle key={`${point.year}-${point.value}`} cx={x} cy={y} r="6" />;
        })}
      </svg>
      <div className="trend-labels">
        {trend.points.map((point) => (
          <span key={point.year}>{point.year}</span>
        ))}
      </div>
    </div>
  );
}

const RISK_LABELS: Record<string, string> = {
  market: "市场",
  financial: "财务",
  operational: "经营",
  legal: "合规",
  other: "其他",
};

function RiskRadar({ profile }: { profile: PortfolioDashboard["risk_heatmap"][number] }) {
  const categories = ["market", "financial", "operational", "legal", "other"];
  const maximum = Math.max(...categories.map((key) => profile.categories[key] ?? 0), 1);
  const center = 100;
  const radius = 72;
  const point = (index: number, scale: number) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / categories.length;
    return `${center + Math.cos(angle) * radius * scale},${center + Math.sin(angle) * radius * scale}`;
  };
  return (
    <article className="radar-card">
      <strong>{profile.company_name}</strong>
      <svg viewBox="0 0 200 200" role="img" aria-label={`${profile.company_name} 风险雷达`}>
        <polygon className="radar-grid" points={categories.map((_, index) => point(index, 1)).join(" ")} />
        {categories.map((category, index) => (
          <line key={category} className="radar-axis" x1="100" y1="100" x2={point(index, 1).split(",")[0]} y2={point(index, 1).split(",")[1]} />
        ))}
        <polygon
          className="radar-value"
          points={categories.map((key, index) => point(index, (profile.categories[key] ?? 0) / maximum)).join(" ")}
        />
        {categories.map((category, index) => {
          const [x, y] = point(index, 1.18).split(",");
          return <text key={category} x={x} y={y}>{RISK_LABELS[category]}</text>;
        })}
      </svg>
      <span className="muted">共 {profile.total} 个风险证据节点</span>
    </article>
  );
}

function PortfolioSelector({
  companies,
  selected,
  busy,
  onToggle,
  onLoad,
}: {
  companies: CompanySummary[];
  selected: string[];
  busy: boolean;
  onToggle: (companyId: string) => void;
  onLoad: () => void;
}) {
  return (
    <div className="stack">
      <div className="company-picker">
        {companies.map((company) => (
          <label key={company.company_id} className="check-card">
            <input
              type="checkbox"
              checked={selected.includes(company.company_id)}
              onChange={() => onToggle(company.company_id)}
            />
            <span>{company.name}</span>
          </label>
        ))}
      </div>
      <button className="primary" type="button" disabled={busy || selected.length < 2} onClick={onLoad}>
        {busy ? "正在聚合…" : `加载 ${selected.length} 家公司组合`}
      </button>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>("research");
  const [health, setHealth] = useState("checking");
  const [error, setError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [question, setQuestion] = useState(SUGGESTED_QUESTIONS[0]);
  const [busy, setBusy] = useState(false);
  const [research, setResearch] = useState<ResearchResponse | null>(null);
  const [companies, setCompanies] = useState<CompanySummary[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [metrics, setMetrics] = useState<MetricObservation[]>([]);
  const [metricKey, setMetricKey] = useState("revenue");
  const [metricTrend, setMetricTrend] = useState<MetricTrend | null>(null);
  const [compareDocA, setCompareDocA] = useState("");
  const [compareDocB, setCompareDocB] = useState("");
  const [comparePeriod, setComparePeriod] = useState("2021");
  const [compareMetricKeys, setCompareMetricKeys] = useState(
    "revenue,net_income,net_cash_from_operating_activities",
  );
  const [comparison, setComparison] = useState<CompareResponse | null>(null);
  const [portfolioCompanyIds, setPortfolioCompanyIds] = useState<string[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioDashboard | null>(null);
  const [reportQuestion, setReportQuestion] = useState("生成年度经营、财务与风险分析提纲");
  const [reportCompanyId, setReportCompanyId] = useState("");
  const [reportStartYear, setReportStartYear] = useState("");
  const [reportEndYear, setReportEndYear] = useState("");
  const [reportType, setReportType] = useState<"investment" | "risk">("investment");
  const [report, setReport] = useState<ReportOutlineResponse | null>(null);
  const [servingEvals, setServingEvals] = useState<ServingEvalSummary[]>([]);
  const [selectedEval, setSelectedEval] = useState<ServingEvalSummary | null>(null);
  const [scorecards, setScorecards] = useState<ScorecardSummary[]>([]);
  const [ingestionJobs, setIngestionJobs] = useState<IngestionJob[]>([]);
  const [ingestionMetrics, setIngestionMetrics] = useState<IngestionQueueMetrics | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadCompany, setUploadCompany] = useState("");
  const [uploadYear, setUploadYear] = useState("2021");

  const selectedDoc = useMemo(
    () => documents.find((item) => item.doc_id === selectedDocId) ?? null,
    [documents, selectedDocId],
  );

  const reportCompany = useMemo(
    () => companies.find((item) => item.company_id === reportCompanyId) ?? null,
    [companies, reportCompanyId],
  );

  const reportDocuments = useMemo(() => {
    const start = Number(reportStartYear) || 0;
    const end = Number(reportEndYear) || 9999;
    return documents
      .filter((item) =>
        item.metadata.company === reportCompany?.name
        && (item.metadata.year ?? 0) >= start
        && (item.metadata.year ?? 0) <= end
        && item.status === "completed",
      )
      .sort((left, right) => (left.metadata.year ?? 0) - (right.metadata.year ?? 0));
  }, [documents, reportCompany, reportEndYear, reportStartYear]);

  const comparisonColumns = useMemo(
    () =>
      Array.from(
        new Set((comparison?.matrix ?? []).flatMap((row) => Object.keys(row))),
      ),
    [comparison],
  );

  const servingDocIds = useMemo(
    () => new Set(servingEvals.map((item) => item.doc_id)),
    [servingEvals],
  );

  const selectedIsServing = Boolean(selectedDocId && servingDocIds.has(selectedDocId));

  function explainWarning(warning: string) {
    if (warning.includes("SQL route returned no matching")) {
      return "当前文档没有匹配到结构化指标。请左侧选择带 Serving 标记的年报（如天华/聚灿/指南针）。";
    }
    if (warning.toLowerCase().includes("timed out") || warning.includes("502")) {
      return "LLM 不可用或超时。已建议改用硅基 chat：确认 .env 中 LLM_MODEL_API_TYPE=silicon 后重启 uvicorn。";
    }
    return warning;
  }

  async function refreshDocuments(preferredIds: Set<string> = new Set()) {
    const docs = await api.listDocuments();
    setDocuments(docs);
    const stillSelected = docs.some((item) => item.doc_id === selectedDocId);
    if (stillSelected) return;
    const servingCompleted = docs.find(
      (item) => preferredIds.has(item.doc_id) && item.status === "completed",
    );
    const anyServing = docs.find((item) => preferredIds.has(item.doc_id));
    const completed = docs.find((item) => item.status === "completed");
    const next = servingCompleted ?? anyServing ?? completed ?? docs[0];
    if (next) setSelectedDocId(next.doc_id);
  }

  async function bootstrap() {
    setError(null);
    try {
      const h = await api.health();
      setHealth(h.status);
      const serving = await api.listServingEvals();
      setServingEvals(serving);
      const servingIds = new Set(serving.map((item) => item.doc_id));
      await refreshDocuments(servingIds);
      const companyList = await api.listCompanies();
      setCompanies(companyList);
      if (companyList[0]) setCompanyId(companyList[0].company_id);
      if (companyList[0]) setReportCompanyId(companyList[0].company_id);
      setPortfolioCompanyIds(companyList.slice(0, 4).map((item) => item.company_id));
      if (serving[0]) {
        const detail = await api.getServingEval(serving[0].doc_id);
        setSelectedEval(detail);
      }
      setScorecards(await api.listScorecards());
      setIngestionJobs(await api.listIngestionJobs());
      setIngestionMetrics(await api.getIngestionMetrics());
    } catch (err) {
      setHealth("down");
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (documents.length === 0) return;
    setCompareDocA((current) =>
      documents.some((item) => item.doc_id === current) ? current : documents[0].doc_id,
    );
    setCompareDocB((current) => {
      if (documents.some((item) => item.doc_id === current)) return current;
      return documents.find((item) => item.doc_id !== documents[0].doc_id)?.doc_id ?? "";
    });
  }, [documents]);

  useEffect(() => {
    const years = reportCompany?.years ?? [];
    if (years.length === 0) return;
    setReportStartYear(String(Math.min(...years)));
    setReportEndYear(String(Math.max(...years)));
  }, [reportCompany]);

  useEffect(() => {
    if (tab !== "jobs") return;
    const refresh = () => {
      void Promise.all([api.listIngestionJobs(), api.getIngestionMetrics()])
        .then(([jobs, queueMetrics]) => {
          setIngestionJobs(jobs);
          setIngestionMetrics(queueMetrics);
          if (jobs.every((job) => ["succeeded", "failed", "cancelled"].includes(job.status))) {
            void refreshDocuments();
          }
        })
        .catch((err) => setError(err instanceof Error ? err.message : String(err)));
    };
    refresh();
    const timer = window.setInterval(refresh, 2000);
    return () => window.clearInterval(timer);
  }, [tab]);

  async function onAsk(event?: FormEvent) {
    event?.preventDefault();
    if (!selectedDocId || !question.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.research(selectedDocId, question.trim(), 5);
      setResearch(result);
      setTab("research");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function loadMetrics(nextCompanyId = companyId) {
    if (!nextCompanyId) return;
    setBusy(true);
    setError(null);
    try {
      const [result, trend] = await Promise.all([
        api.queryMetrics(nextCompanyId, metricKey),
        api.metricTrend(nextCompanyId, metricKey),
      ]);
      setMetrics(result.items ?? []);
      setMetricTrend(trend);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onCompare(event: FormEvent) {
    event.preventDefault();
    if (!compareDocA || !compareDocB || compareDocA === compareDocB) return;
    setBusy(true);
    setError(null);
    try {
      setComparison(
        await api.compareDocuments({
          doc_id_a: compareDocA,
          doc_id_b: compareDocB,
          question: "比较两份文档的核心财务指标与风险差异",
          period: comparePeriod || null,
          metric_keys: compareMetricKeys
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          use_workflow: true,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function togglePortfolioCompany(nextCompanyId: string) {
    setPortfolioCompanyIds((current) =>
      current.includes(nextCompanyId)
        ? current.filter((item) => item !== nextCompanyId)
        : [...current, nextCompanyId],
    );
  }

  async function loadPortfolio() {
    if (portfolioCompanyIds.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      setPortfolio(
        await api.portfolioDashboard(portfolioCompanyIds, [
          "revenue",
          "net_income",
          "total_assets",
        ]),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onGenerateReport(event: FormEvent) {
    event.preventDefault();
    const previewDoc = reportDocuments.at(-1);
    if (!previewDoc || !reportQuestion.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setReport(
        await api.reportOutline({
          doc_id: previewDoc.doc_id,
          question: reportQuestion.trim(),
          top_k: 8,
          use_workflow: true,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onExportReport(format: "html" | "pdf") {
    if (!report || reportDocuments.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const company = reportCompany?.name || "research-report";
      const period = reportStartYear === reportEndYear
        ? reportStartYear
        : `${reportStartYear}-${reportEndYear}`;
      const artifact = await api.reportBundleExport({
        doc_ids: reportDocuments.map((item) => item.doc_id),
        question: reportQuestion.trim(),
        top_k: 8,
        report_type: reportType,
        title: `${company}-${period}-${reportType === "investment" ? "投研" : "风控"}报告`,
        format,
      });
      downloadBlob(artifact.filename, artifact.blob);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function openServingEval(docId: string) {
    setBusy(true);
    setError(null);
    try {
      setSelectedEval(await api.getServingEval(docId));
      setTab("eval");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    if (!uploadFile) return;
    setBusy(true);
    setError(null);
    try {
      const job = await api.uploadDocumentAsync(uploadFile, {
        company: uploadCompany,
        year: uploadYear,
        doc_type: "annual_report",
        source: "web_console",
      });
      setIngestionJobs((current) => [job, ...current.filter((item) => item.job_id !== job.job_id)]);
      await refreshDocuments();
      setSelectedDocId(job.doc_id);
      setTab("jobs");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <h1>Claude Copilot</h1>
          <p>金融文档工作台 · 文档 / 问答 / 评测</p>
        </div>

        <div className="panel stack">
          <div className="row">
            <span className={health === "ok" ? "chip good" : "chip bad"}>
              API {health}
            </span>
            <button type="button" className="primary" onClick={() => void bootstrap()}>
              刷新
            </button>
          </div>
          <p className="hint">默认展示卡片与表格；原始 JSON 折叠在详情中。</p>
        </div>

        <div className="panel">
          <h2>已入库文档</h2>
          <div className="doc-list">
            {documents.length === 0 && <p className="muted">暂无文档。请先 Serving 入库或上传。</p>}
            {documents.map((doc) => (
              <button
                key={doc.doc_id}
                type="button"
                className={`doc-item ${doc.doc_id === selectedDocId ? "active" : ""}`}
                onClick={() => setSelectedDocId(doc.doc_id)}
              >
                <strong>{doc.metadata.company || doc.filename}</strong>
                <span className="muted">
                  {doc.metadata.year ?? "—"} · segments {doc.segment_count}
                </span>
                <div className="row" style={{ marginTop: 6 }}>
                  <span className={statusChip(doc.status)}>{doc.status}</span>
                  {servingDocIds.has(doc.doc_id) && <span className="chip good">Serving</span>}
                  <span className="chip">{doc.doc_id.slice(0, 8)}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="panel">
          <h2>L3 评测摘要</h2>
          <div className="stack">
            {servingEvals.slice(0, 5).map((item) => (
              <button
                key={item.doc_id}
                type="button"
                className="doc-item"
                onClick={() => void openServingEval(item.doc_id)}
              >
                <strong>{item.doc_id.slice(0, 12)}…</strong>
                <span className="muted">
                  pass_rate {item.l3?.pass_rate ?? "—"} ({item.l3?.passed}/{item.l3?.total})
                </span>
              </button>
            ))}
            {servingEvals.length === 0 && <p className="muted">尚无 serving_eval 报告。</p>}
          </div>
        </div>
      </aside>

      <main className="main">
        {error && <div className="error-banner">{error}</div>}

        <div className="tabs">
          {(
            [
              ["research", "研究问答"],
              ["compare", "对比看板"],
              ["reports", "报告中心"],
              ["metrics", "BI 指标"],
              ["eval", "评测看板"],
              ["jobs", "处理任务"],
              ["upload", "上传"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={tab === id ? "active" : ""}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "research" && (
          <section className="panel stack">
            <h2>研究问答</h2>
            <p className="muted">
              当前文档：
              {selectedDoc
                ? `${selectedDoc.metadata.company || selectedDoc.filename} (${selectedDoc.doc_id.slice(0, 8)})`
                : "未选择"}
              {selectedDoc && (
                <>
                  {" · "}
                  {selectedIsServing ? (
                    <span className="chip good">Serving 已入库</span>
                  ) : (
                    <span className="chip warn">非 Serving 文档，指标可能为空</span>
                  )}
                </>
              )}
            </p>
            <form className="stack" onSubmit={(event) => void onAsk(event)}>
              <div className="field">
                <label htmlFor="question">问题</label>
                <textarea
                  id="question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                />
              </div>
              <div className="row">
                {SUGGESTED_QUESTIONS.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className="chip"
                    onClick={() => setQuestion(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <button className="primary" type="submit" disabled={busy || !selectedDocId}>
                {busy ? "检索中…" : "提问"}
              </button>
            </form>

            {research && (
              <div className="stack">
                <div className="row">
                  <span className="chip">{research.query_analysis?.intent ?? "—"}</span>
                  {(research.query_analysis?.routes ?? []).map((route) => (
                    <span key={route} className="chip good">
                      {route}
                    </span>
                  ))}
                  {typeof research.grounded === "boolean" && (
                    <span className={research.grounded ? "chip good" : "chip warn"}>
                      grounded={String(research.grounded)}
                    </span>
                  )}
                </div>

                {research.fusion_summary && (
                  <div className="panel fusion-panel">
                    <h3>混合检索摘要</h3>
                    <div className="row">
                      <span className="chip">
                        {formatFusionIntent(research.fusion_summary.query_intent)}
                      </span>
                      {research.fusion_summary.routes.map((route) => (
                        <span key={route} className="chip good">
                          {formatFusionRoute(route)}
                        </span>
                      ))}
                      <span className="chip muted-chip">
                        语义 {research.fusion_summary.vector_snippet_count}
                      </span>
                      <span className="chip muted-chip">
                        指标 {research.fusion_summary.metric_count}
                      </span>
                      <span className="chip muted-chip">
                        图谱 {research.fusion_summary.graph_path_count}
                      </span>
                    </div>
                    {research.fusion_summary.summary && (
                      <p className="fusion-summary">{research.fusion_summary.summary}</p>
                    )}
                    {(research.fusion_summary.highlights?.length ?? 0) > 0 && (
                      <ul className="fusion-highlights">
                        {research.fusion_summary.highlights.slice(0, 6).map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                <div className="panel">
                  <h3>回答</h3>
                  <div className="answer">
                    {research.synthesis?.answer || research.answer || "（无合成答案，见下方证据）"}
                  </div>
                </div>

                {(research.metrics?.length ?? 0) > 0 && (
                  <div>
                    <h3>结构化指标</h3>
                    <div className="metric-grid">
                      {research.metrics!.map((metric, index) => (
                        <div className="metric-card" key={`${metric.metric_key}-${metric.period}-${index}`}>
                          <div className="muted">
                            {metric.metric_key} · {metric.period}
                          </div>
                          <div className="value">{formatValue(metric.value)}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {(research.hits?.length ?? 0) > 0 && (
                  <div>
                    <h3>语义命中</h3>
                    <div className="hit-list">
                      {research.hits!.slice(0, 5).map((hit) => (
                        <div className="hit-card" key={hit.segment_id}>
                          <div className="row">
                            <span className="chip">score {hit.score.toFixed(3)}</span>
                            <span className="muted">{hit.segment_id}</span>
                          </div>
                          <pre>{hit.content.slice(0, 320)}{hit.content.length > 320 ? "…" : ""}</pre>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {(research.graph_paths?.length ?? 0) > 0 && (
                  <div>
                    <h3>图谱路径</h3>
                    <div className="hit-list">
                      {research.graph_paths!.map((path) => (
                        <div className="hit-card" key={path.path_id}>
                          <div className="row">
                            <span className="chip">score {path.score.toFixed(3)}</span>
                          </div>
                          <div>{path.summary}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {(research.warnings?.length ?? 0) > 0 && (
                  <div className="panel">
                    <h3>Warnings</h3>
                    <ul>
                      {research.warnings!.map((warning) => (
                        <li key={warning}>
                          <div>{explainWarning(warning)}</div>
                          <div className="muted" style={{ fontSize: "0.85rem" }}>
                            {warning}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <details>
                  <summary>原始 JSON</summary>
                  <pre className="raw-json">{JSON.stringify(research, null, 2)}</pre>
                </details>
              </div>
            )}
          </section>
        )}

        {tab === "compare" && (
          <section className="stack">
            <div className="panel stack">
              <div className="row spread">
                <div>
                  <h2>跨文档对比看板</h2>
                  <p className="muted">选择两份真实入库文档，生成指标矩阵、差异摘要和风险提示。</p>
                </div>
                {comparison && <span className="chip good">{comparison.workflow}</span>}
              </div>
              <form className="stack" onSubmit={(event) => void onCompare(event)}>
                <div className="row">
                  <div className="field">
                    <label htmlFor="compare-a">文档 A</label>
                    <select
                      id="compare-a"
                      value={compareDocA}
                      onChange={(event) => setCompareDocA(event.target.value)}
                    >
                      {documents.map((doc) => (
                        <option key={doc.doc_id} value={doc.doc_id}>
                          {doc.metadata.company || doc.filename} · {doc.metadata.year ?? "—"}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="compare-b">文档 B</label>
                    <select
                      id="compare-b"
                      value={compareDocB}
                      onChange={(event) => setCompareDocB(event.target.value)}
                    >
                      <option value="">请选择第二份文档</option>
                      {documents.map((doc) => (
                        <option key={doc.doc_id} value={doc.doc_id}>
                          {doc.metadata.company || doc.filename} · {doc.metadata.year ?? "—"}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field compact-field">
                    <label htmlFor="compare-period">期间</label>
                    <input
                      id="compare-period"
                      value={comparePeriod}
                      onChange={(event) => setComparePeriod(event.target.value)}
                    />
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="compare-metrics">指标键（逗号分隔）</label>
                  <input
                    id="compare-metrics"
                    value={compareMetricKeys}
                    onChange={(event) => setCompareMetricKeys(event.target.value)}
                  />
                </div>
                {compareDocA === compareDocB && compareDocA && (
                  <div className="error-banner">文档 A 与 B 必须不同。</div>
                )}
                <button
                  className="primary"
                  type="submit"
                  disabled={busy || !compareDocA || !compareDocB || compareDocA === compareDocB}
                >
                  {busy ? "正在比较…" : "运行对比工作流"}
                </button>
              </form>
            </div>

            {comparison && (
              <div className="panel stack">
                <h3>指标矩阵</h3>
                {comparison.matrix.length > 0 ? (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          {comparisonColumns.map((column) => <th key={column}>{column}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {comparison.matrix.map((row, rowIndex) => (
                          <tr key={rowIndex}>
                            {comparisonColumns.map((column) => (
                              <td key={column}>{formatValue(row[column] as number | string | null)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="muted">工作流未返回可比较的结构化指标。</p>
                )}
                <div className="dashboard-grid">
                  <div className="metric-card">
                    <h3>差异摘要</h3>
                    <ul>{comparison.highlights.map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                  <div className="metric-card">
                    <h3>风险与限制</h3>
                    <ul>{comparison.warnings.map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                </div>
                <div className="answer markdown-output">{comparison.answer_markdown}</div>
              </div>
            )}
            <div className="panel stack">
              <div>
                <h2>多公司对比</h2>
                <p className="muted">组合 SQL 财务事实与知识图谱证据，生成公司排名、风险雷达和业务重叠度。</p>
              </div>
              <PortfolioSelector
                companies={companies}
                selected={portfolioCompanyIds}
                busy={busy}
                onToggle={togglePortfolioCompany}
                onLoad={() => void loadPortfolio()}
              />
            </div>
            {portfolio && (
              <div className="panel stack">
                <h3>财务对比排名</h3>
                <div className="dashboard-grid">
                  {portfolio.rankings.map((ranking) => {
                    const maximum = Math.max(...ranking.items.map((item) => Math.abs(item.value)), 1);
                    return (
                      <article className="metric-card" key={ranking.metric_key}>
                        <strong>{ranking.metric_key}</strong>
                        <div className="bar-list">
                          {ranking.items.map((item) => (
                            <div key={item.company_id}>
                              <div className="row spread"><span>{item.company_name}</span><span>{formatValue(item.value)}</span></div>
                              <div className="bar-track"><span style={{ width: `${Math.max(4, Math.abs(item.value) / maximum * 100)}%` }} /></div>
                            </div>
                          ))}
                        </div>
                      </article>
                    );
                  })}
                </div>
                <h3>风险雷达</h3>
                <div className="radar-grid-layout">
                  {portfolio.risk_heatmap.map((profile) => <RiskRadar key={profile.company_id} profile={profile} />)}
                </div>
                <h3>业务重叠度</h3>
                <div className="table-scroll">
                  <table><thead><tr><th>公司组合</th><th>重叠业务</th><th>Jaccard</th></tr></thead><tbody>
                    {portfolio.business_overlap.map((item) => (
                      <tr key={`${item.company_id_a}-${item.company_id_b}`}>
                        <td>{item.company_id_a} ↔ {item.company_id_b}</td>
                        <td>{item.shared_segments.join("、") || "无已识别重叠"}</td>
                        <td>{(item.score * 100).toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody></table>
                </div>
              </div>
            )}
          </section>
        )}

        {tab === "reports" && (
          <section className="stack">
            <div className="panel stack">
              <div className="row spread">
                <div>
                  <h2>自动报告中心</h2>
                  <p className="muted">基于当前选中文档生成可审阅提纲，并导出 Markdown、HTML 或 PDF。</p>
                </div>
                {report && (
                  <div className="row">
                    <button
                      type="button"
                      onClick={() => downloadMarkdown(
                        `${selectedDoc?.metadata.company || "research-report"}-${selectedDoc?.metadata.year || ""}.md`,
                        report.answer_markdown,
                      )}
                    >
                      Markdown
                    </button>
                    <button type="button" disabled={busy} onClick={() => void onExportReport("html")}>
                      HTML
                    </button>
                    <button className="primary" type="button" disabled={busy} onClick={() => void onExportReport("pdf")}>
                      PDF
                    </button>
                  </div>
                )}
              </div>
              <div className="row">
                <div className="field">
                  <label htmlFor="report-company">公司</label>
                  <select id="report-company" value={reportCompanyId} onChange={(event) => setReportCompanyId(event.target.value)}>
                    {companies.map((company) => <option key={company.company_id} value={company.company_id}>{company.name}</option>)}
                  </select>
                </div>
                <div className="field compact-field">
                  <label htmlFor="report-start-year">起始年度</label>
                  <input id="report-start-year" inputMode="numeric" value={reportStartYear} onChange={(event) => setReportStartYear(event.target.value)} />
                </div>
                <div className="field compact-field">
                  <label htmlFor="report-end-year">结束年度</label>
                  <input id="report-end-year" inputMode="numeric" value={reportEndYear} onChange={(event) => setReportEndYear(event.target.value)} />
                </div>
                <div className="field compact-field">
                  <label htmlFor="report-type">报告类型</label>
                  <select id="report-type" value={reportType} onChange={(event) => setReportType(event.target.value as "investment" | "risk")}>
                    <option value="investment">投资研究</option>
                    <option value="risk">风险控制</option>
                  </select>
                </div>
              </div>
              <p className="muted">匹配到 {reportDocuments.length} 份已完成文档；预览使用最新年度，HTML/PDF 合并整个时间范围。</p>
              <form className="stack" onSubmit={(event) => void onGenerateReport(event)}>
                <div className="field">
                  <label htmlFor="report-question">报告目标</label>
                  <textarea
                    id="report-question"
                    value={reportQuestion}
                    onChange={(event) => setReportQuestion(event.target.value)}
                  />
                </div>
                <button className="primary" type="submit" disabled={busy || reportDocuments.length === 0}>
                  {busy ? "正在生成…" : "生成报告提纲"}
                </button>
              </form>
            </div>
            {report && (
              <div className="panel stack">
                <div className="row">
                  <span className="chip good">{report.workflow}</span>
                  <span className="chip">{report.sections.length} sections</span>
                </div>
                <div className="report-sections">
                  {report.sections.map((section, index) => (
                    <article className="report-card" key={index}>
                      <strong>{String(section.title ?? section.heading ?? `Section ${index + 1}`)}</strong>
                      <p>{String(section.summary ?? section.content ?? section.description ?? "待补充")}</p>
                    </article>
                  ))}
                </div>
                {report.warnings.length > 0 && (
                  <div className="callout warn"><ul>{report.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div>
                )}
                <div className="answer markdown-output">{report.answer_markdown}</div>
              </div>
            )}
          </section>
        )}

        {tab === "metrics" && (
          <section className="panel stack">
            <div>
              <h2>BI 指标趋势</h2>
              <p className="muted">选择公司与标准指标，查看年度趋势、同比、CAGR 与数据质量 warning。</p>
            </div>
            <div className="row">
              <div className="field">
                <label htmlFor="company">公司</label>
                <select
                  id="company"
                  value={companyId}
                  onChange={(event) => setCompanyId(event.target.value)}
                >
                  {companies.map((company) => (
                    <option key={company.company_id} value={company.company_id}>
                      {company.name} ({company.company_id})
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="metric-key">指标</label>
                <select
                  id="metric-key"
                  value={metricKey}
                  onChange={(event) => setMetricKey(event.target.value)}
                >
                  <option value="revenue">营业收入</option>
                  <option value="net_income">净利润</option>
                  <option value="net_cash_from_operating_activities">经营现金流净额</option>
                  <option value="total_assets">总资产</option>
                  <option value="total_equity">所有者权益</option>
                </select>
              </div>
              <button
                type="button"
                className="primary"
                disabled={!companyId || busy}
                onClick={() => void loadMetrics()}
              >
                加载趋势
              </button>
            </div>
            {metricTrend && (
              <div className="stack">
                <div className="dashboard-grid">
                  <div className="metric-card">
                    <div className="muted">最新值</div>
                    <div className="value">
                      {formatValue(metricTrend.points.at(-1)?.value)} {metricTrend.unit ?? ""}
                    </div>
                  </div>
                  <div className="metric-card">
                    <div className="muted">CAGR</div>
                    <div className="value">
                      {metricTrend.cagr == null ? "—" : `${(metricTrend.cagr * 100).toFixed(2)}%`}
                    </div>
                  </div>
                  <div className="metric-card">
                    <div className="muted">数据点</div>
                    <div className="value">{metricTrend.points.length}</div>
                  </div>
                </div>
                <TrendChart trend={metricTrend} />
                {metricTrend.warnings.length > 0 && (
                  <div className="callout warn">
                    <ul>{metricTrend.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
                  </div>
                )}
              </div>
            )}
            <table>
              <thead>
                <tr>
                  <th>metric</th>
                  <th>period</th>
                  <th>value</th>
                  <th>document</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((metric, index) => (
                  <tr key={`${metric.metric_key}-${metric.period}-${index}`}>
                    <td>{metric.metric_key}</td>
                    <td>{metric.period}</td>
                    <td>{formatValue(metric.value)}</td>
                    <td>{metric.document_id?.slice(0, 12) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {metrics.length === 0 && <p className="muted">选择公司后加载指标。</p>}
            <hr />
            <div>
              <h2>Portfolio BI</h2>
              <p className="muted">选择至少两家公司，查看行业分布、公司排名和风险热力图。</p>
            </div>
            <PortfolioSelector
              companies={companies}
              selected={portfolioCompanyIds}
              busy={busy}
              onToggle={togglePortfolioCompany}
              onLoad={() => void loadPortfolio()}
            />
            {portfolio && (
              <div className="stack">
                <div className="dashboard-grid">
                  {portfolio.industry_distribution.map((item) => (
                    <article className="metric-card" key={item.industry}>
                      <div className="muted">行业分布</div>
                      <div className="value">{item.industry}</div>
                      <div>{item.company_count} 家公司</div>
                    </article>
                  ))}
                </div>
                <h3>公司排名</h3>
                <div className="table-scroll">
                  <table><thead><tr><th>指标</th><th>排名</th><th>公司</th><th>最新值</th><th>年度</th></tr></thead><tbody>
                    {portfolio.rankings.flatMap((ranking) => ranking.items.map((item, index) => (
                      <tr key={`${ranking.metric_key}-${item.company_id}`}>
                        <td>{ranking.metric_key}</td><td>{index + 1}</td><td>{item.company_name}</td>
                        <td>{formatValue(item.value)} {item.unit ?? ""}</td><td>{item.year}</td>
                      </tr>
                    )))}
                  </tbody></table>
                </div>
                <h3>风险热力图</h3>
                <div className="table-scroll risk-heatmap">
                  <table><thead><tr><th>公司</th>{Object.values(RISK_LABELS).map((label) => <th key={label}>{label}</th>)}<th>合计</th></tr></thead><tbody>
                    {portfolio.risk_heatmap.map((profile) => (
                      <tr key={profile.company_id}><td>{profile.company_name}</td>
                        {Object.keys(RISK_LABELS).map((key) => <td key={key} data-level={Math.min(profile.categories[key] ?? 0, 3)}>{profile.categories[key] ?? 0}</td>)}
                        <td>{profile.total}</td>
                      </tr>
                    ))}
                  </tbody></table>
                </div>
                {portfolio.warnings.length > 0 && <div className="callout warn"><ul>{portfolio.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div>}
              </div>
            )}
          </section>
        )}

        {tab === "eval" && (
          <section className="stack">
            <div className="panel stack">
              <h2>Serving / L3</h2>
              {selectedEval ? (
                <>
                  <div className="row">
                    <span className="chip">{selectedEval.doc_id}</span>
                    <span
                      className={
                        (selectedEval.l3?.pass_rate ?? 0) >= 1 ? "chip good" : "chip warn"
                      }
                    >
                      pass_rate {selectedEval.l3?.pass_rate ?? "—"}
                    </span>
                    <span className="chip">
                      {selectedEval.l3?.passed}/{selectedEval.l3?.total}
                    </span>
                  </div>
                  <div className="case-list">
                    {(selectedEval.cases ?? []).map((item) => (
                      <div className="case-card" key={item.id ?? item.question}>
                        <div className="row">
                          <span className={item.passed ? "chip good" : "chip bad"}>
                            {item.passed ? "PASS" : "FAIL"}
                          </span>
                          <span className="chip">{item.expect_route}</span>
                          <span className="muted">{item.id}</span>
                        </div>
                        <div>{item.question}</div>
                        <div className="muted">
                          intent={item.actual_intent ?? "—"} · route_ok={String(item.route_ok)} ·
                          metric_ok={String(item.metric_ok)} · semantic_ok={String(item.semantic_ok)} ·
                          graph_ok={String(item.graph_ok)}
                        </div>
                        {item.matched_metric && (
                          <div>
                            {item.matched_metric.metric_key} {item.matched_metric.period} ={" "}
                            {formatValue(item.matched_metric.value)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                  <details>
                    <summary>原始 JSON</summary>
                    <pre className="raw-json">{JSON.stringify(selectedEval, null, 2)}</pre>
                  </details>
                </>
              ) : (
                <p className="muted">左侧选择一份 serving eval。</p>
              )}
            </div>

            <div className="panel">
              <h2>Scorecards</h2>
              <table>
                <thead>
                  <tr>
                    <th>name</th>
                    <th>core_exact</th>
                    <th>grounding</th>
                    <th>gate</th>
                  </tr>
                </thead>
                <tbody>
                  {scorecards.map((card) => (
                    <tr key={card.name}>
                      <td>{card.name}</td>
                      <td>{formatValue(card.summary_scores?.core_metric_exact_match ?? null)}</td>
                      <td>{formatValue(card.summary_scores?.source_grounding_rate ?? null)}</td>
                      <td>
                        {card.serving_gate?.allow_metric_serving ? (
                          <span className="chip good">allow</span>
                        ) : (
                          <span className="chip bad">block</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {tab === "jobs" && (
          <section className="stack">
            <div className="panel stack">
              <div className="row spread">
                <div>
                  <h2>文档处理任务</h2>
                  <p className="muted">真实展示队列、执行阶段、重试次数和运行事件，每 2 秒刷新。</p>
                </div>
                <div className="row">
                    <span className="chip">
                      健康 {ingestionMetrics?.health_status ?? "unknown"} · Worker{" "}
                      {ingestionMetrics?.active_worker_count ?? 0} · 运行中{" "}
                      {ingestionMetrics?.status_counts.running ?? 0}
                  </span>
                  <span className="chip warn">
                    排队 {(ingestionMetrics?.status_counts.queued ?? 0) + (ingestionMetrics?.status_counts.retry_wait ?? 0)}
                  </span>
                  <span className="chip good">
                    完成 {ingestionMetrics?.status_counts.succeeded ?? 0}
                  </span>
                  {(ingestionMetrics?.cancellation_requested_count ?? 0) > 0 && (
                    <span className="chip warn">
                      待取消 {ingestionMetrics?.cancellation_requested_count}
                    </span>
                  )}
                  </div>
                </div>
                {(ingestionMetrics?.alerts.length ?? 0) > 0 && (
                  <div className="callout warn">
                    {ingestionMetrics?.alerts.map((alert) => (
                      <div key={alert.code}>
                        <strong>{alert.severity.toUpperCase()}</strong> · {alert.message}（当前{" "}
                        {alert.observed_value} / 阈值 {alert.threshold}）
                      </div>
                    ))}
                  </div>
                )}
                {ingestionJobs.length === 0 && <p className="muted">尚无异步处理任务。</p>}
              <div className="job-list">
                {ingestionJobs.map((job) => (
                  <article className="job-card" key={job.job_id}>
                    <div className="row spread">
                      <div>
                        <strong>{job.filename}</strong>
                        <div className="muted">
                          job {job.job_id.slice(0, 8)} · doc {job.doc_id.slice(0, 8)}
                        </div>
                      </div>
                      <div className="row">
                        <span className={statusChip(job.status)}>{job.status}</span>
                        <span className="chip">{job.stage}</span>
                        <span className="chip">
                          尝试 {job.attempt}/{job.max_attempts}
                        </span>
                      </div>
                    </div>
                    <div className="progress-track" aria-label={`处理进度 ${job.progress_percent}%`}>
                      <div className="progress-value" style={{ width: `${job.progress_percent}%` }} />
                    </div>
                    <div className="row spread muted">
                      <span>{job.progress_percent}%</span>
                      <span>{new Date(job.updated_at).toLocaleString("zh-CN")}</span>
                    </div>
                    {job.error_message && <div className="error-banner">{job.error_message}</div>}
                    <details>
                      <summary>执行轨迹（{job.events.length}）</summary>
                      <ol className="event-list">
                        {job.events.map((event, index) => (
                          <li key={`${event.timestamp}-${index}`}>
                            <span className={statusChip(event.status)}>{event.status}</span>{" "}
                            <strong>{event.stage ?? "—"}</strong> · {event.progress_percent}% ·{" "}
                            {new Date(event.timestamp).toLocaleTimeString("zh-CN")}
                            {event.message ? ` · ${event.message}` : ""}
                          </li>
                        ))}
                      </ol>
                    </details>
                  </article>
                ))}
              </div>
            </div>
          </section>
        )}

        {tab === "upload" && (
          <section className="panel">
            <h2>上传金融文档</h2>
            <form className="stack" onSubmit={(event) => void onUpload(event)}>
              <div className="field">
                <label htmlFor="file">文件</label>
                <input
                  id="file"
                  type="file"
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.html,.htm,.md,.txt"
                  onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                />
              </div>
              <div className="row">
                <div className="field">
                  <label htmlFor="companyName">公司</label>
                  <input
                    id="companyName"
                    value={uploadCompany}
                    onChange={(event) => setUploadCompany(event.target.value)}
                    placeholder="例如：某某股份有限公司"
                  />
                </div>
                <div className="field">
                  <label htmlFor="year">年份</label>
                  <input
                    id="year"
                    value={uploadYear}
                    onChange={(event) => setUploadYear(event.target.value)}
                  />
                </div>
              </div>
              <button className="primary" type="submit" disabled={!uploadFile || busy}>
                {busy ? "正在创建任务…" : "上传并加入处理队列"}
              </button>
              <p className="hint">文件归档后立即返回任务 ID；解析、Schema、索引和图谱在后台执行。</p>
            </form>
          </section>
        )}
      </main>
    </div>
  );
}
