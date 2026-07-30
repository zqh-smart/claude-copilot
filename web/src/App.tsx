import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { api } from "./api";
import type {
  CompanySummary,
  DocumentRecord,
  ResearchResponse,
  ScorecardSummary,
  ServingEvalSummary,
} from "./api";
import "./index.css";

type Tab = "research" | "metrics" | "eval" | "upload";

const SUGGESTED_QUESTIONS = [
  "2021年营业收入是多少？",
  "管理层如何讨论与分析公司经营情况？",
  "公司面临哪些市场风险或风险暴露？",
];

function statusChip(status: string) {
  if (status === "completed") return "chip good";
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
  const [metrics, setMetrics] = useState<
    { metric_key: string; period: string; value: number | string }[]
  >([]);
  const [servingEvals, setServingEvals] = useState<ServingEvalSummary[]>([]);
  const [selectedEval, setSelectedEval] = useState<ServingEvalSummary | null>(null);
  const [scorecards, setScorecards] = useState<ScorecardSummary[]>([]);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadCompany, setUploadCompany] = useState("");
  const [uploadYear, setUploadYear] = useState("2021");

  const selectedDoc = useMemo(
    () => documents.find((item) => item.doc_id === selectedDocId) ?? null,
    [documents, selectedDocId],
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
      if (serving[0]) {
        const detail = await api.getServingEval(serving[0].doc_id);
        setSelectedEval(detail);
      }
      setScorecards(await api.listScorecards());
    } catch (err) {
      setHealth("down");
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void bootstrap();
  }, []);

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
      const result = await api.queryMetrics(nextCompanyId, "revenue");
      setMetrics(result.items ?? []);
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
      const record = await api.uploadDocument(uploadFile, {
        company: uploadCompany,
        year: uploadYear,
        doc_type: "annual_report",
        source: "web_console",
      });
      await refreshDocuments();
      setSelectedDocId(record.doc_id);
      setTab("research");
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
              ["metrics", "指标"],
              ["eval", "评测看板"],
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

        {tab === "metrics" && (
          <section className="panel stack">
            <h2>公司指标</h2>
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
              <button
                type="button"
                className="primary"
                disabled={!companyId || busy}
                onClick={() => void loadMetrics()}
              >
                加载 revenue
              </button>
            </div>
            <table>
              <thead>
                <tr>
                  <th>metric</th>
                  <th>period</th>
                  <th>value</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((metric, index) => (
                  <tr key={`${metric.metric_key}-${metric.period}-${index}`}>
                    <td>{metric.metric_key}</td>
                    <td>{metric.period}</td>
                    <td>{formatValue(metric.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {metrics.length === 0 && <p className="muted">选择公司后加载指标。</p>}
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

        {tab === "upload" && (
          <section className="panel">
            <h2>上传年报 PDF</h2>
            <form className="stack" onSubmit={(event) => void onUpload(event)}>
              <div className="field">
                <label htmlFor="file">PDF</label>
                <input
                  id="file"
                  type="file"
                  accept="application/pdf,.pdf"
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
                {busy ? "上传处理中…" : "上传并入库"}
              </button>
              <p className="hint">上传会走完整 pipeline，耗时取决于 PDF 页数与 embedding。</p>
            </form>
          </section>
        )}
      </main>
    </div>
  );
}
