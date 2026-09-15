import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, PointerEvent as ReactPointerEvent } from "react";
import { api } from "./api";
import type {
  DocumentKnowledgeGraph,
  DocumentRecord,
  DocumentSegment,
  KnowledgeGraphNode,
  KnowledgeGraphRelationship,
  ResearchResponse,
} from "./api";

type KbView = "library" | "detail";
type DetailTab = "segments" | "hit" | "graph";

const NODE_COLORS: Record<string, string> = {
  company: "#1f5c45",
  document: "#2f6f9f",
  metric: "#8a4b12",
  risk: "#8b2e2e",
  statement: "#5a4b8a",
  section: "#4a6b3a",
  other: "#5a6458",
};

const HIT_SUGGESTIONS = [
  "2021年营业收入是多少？",
  "管理层如何讨论与分析公司经营情况？",
  "公司面临哪些市场风险或风险暴露？",
];

function statusChip(status: string) {
  if (status === "completed" || status === "succeeded") return "chip good";
  if (status === "failed") return "chip bad";
  return "chip warn";
}

function isWorkbenchDoc(doc: DocumentRecord) {
  const name = (doc.filename || "").toLowerCase();
  if (
    name.includes("worker-soak")
    || name.includes("smoke")
    || name.endsWith(".md")
    || name.endsWith(".txt")
  ) {
    return false;
  }
  return doc.segment_count > 0 || Boolean(doc.metadata.company);
}

function formatWhen(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function segmentPreview(content: string, max = 220) {
  const text = content.replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function layoutGraph(nodes: KnowledgeGraphNode[], width: number, height: number) {
  const groups = new Map<string, KnowledgeGraphNode[]>();
  for (const node of nodes) {
    const key = node.node_type || "other";
    const bucket = groups.get(key) ?? [];
    bucket.push(node);
    groups.set(key, bucket);
  }
  const types = Array.from(groups.keys());
  const positions = new Map<string, { x: number; y: number }>();
  types.forEach((type, typeIndex) => {
    const bucket = groups.get(type) ?? [];
    const cx = width * ((typeIndex + 1) / (types.length + 1));
    bucket.forEach((node, index) => {
      const spread = Math.min(height - 80, Math.max(40, bucket.length * 18));
      const y =
        height / 2
        + (index - (bucket.length - 1) / 2) * (spread / Math.max(bucket.length, 1));
      positions.set(node.node_id, { x: cx, y });
    });
  });
  return positions;
}

function KnowledgeGraphCanvas({
  graph,
  selectedNodeId,
  onSelectNode,
}: {
  graph: DocumentKnowledgeGraph;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
}) {
  const width = 960;
  const height = 520;
  const svgRef = useRef<SVGSVGElement | null>(null);
  const nodes = graph.nodes.slice(0, 80);
  const nodeIds = new Set(nodes.map((node) => node.node_id));
  const relationships = graph.relationships
    .filter((rel) => nodeIds.has(rel.source_node_id) && nodeIds.has(rel.target_node_id))
    .slice(0, 120);
  const [positions, setPositions] = useState(() => layoutGraph(nodes, width, height));
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const dragRef = useRef<{ id: string; dx: number; dy: number } | null>(null);

  useEffect(() => {
    setPositions(layoutGraph(nodes, width, height));
  }, [graph.document_id, nodes.length]);

  const visibleTypes = useMemo(
    () => Array.from(new Set(nodes.map((node) => node.node_type || "other"))),
    [nodes],
  );

  const visibleNodeIds = useMemo(() => {
    if (typeFilter === "all") return nodeIds;
    return new Set(
      nodes.filter((node) => (node.node_type || "other") === typeFilter).map((n) => n.node_id),
    );
  }, [nodes, nodeIds, typeFilter]);

  const truncated =
    graph.nodes.length > nodes.length || graph.relationships.length > relationships.length;

  function clientToSvg(event: ReactPointerEvent<SVGElement>) {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const matrix = svg.getScreenCTM();
    if (!matrix) return { x: 0, y: 0 };
    const local = point.matrixTransform(matrix.inverse());
    return { x: local.x, y: local.y };
  }

  function onPointerDown(nodeId: string, event: ReactPointerEvent<SVGGElement>) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = clientToSvg(event);
    const current = positions.get(nodeId) ?? { x: 0, y: 0 };
    dragRef.current = { id: nodeId, dx: current.x - point.x, dy: current.y - point.y };
    onSelectNode(nodeId);
  }

  function onPointerMove(event: ReactPointerEvent<SVGGElement>) {
    const drag = dragRef.current;
    if (!drag) return;
    const point = clientToSvg(event);
    const next = {
      x: Math.min(width - 24, Math.max(24, point.x + drag.dx)),
      y: Math.min(height - 24, Math.max(24, point.y + drag.dy)),
    };
    setPositions((current) => {
      const copy = new Map(current);
      copy.set(drag.id, next);
      return copy;
    });
  }

  function onPointerUp(event: ReactPointerEvent<SVGGElement>) {
    if (dragRef.current) {
      event.currentTarget.releasePointerCapture(event.pointerId);
      dragRef.current = null;
    }
  }

  if (nodes.length === 0) {
    return <p className="muted">该文档暂无知识图谱节点（可能尚未完成 indexing / graph 构建）。</p>;
  }

  return (
    <div className="kb-graph-wrap">
      <div className="row" style={{ marginBottom: 8 }}>
        <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
          <option value="all">全部类型</option>
          {visibleTypes.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
        <button type="button" onClick={() => setPositions(layoutGraph(nodes, width, height))}>
          重置布局
        </button>
        {truncated && (
          <span className="muted">
            截断展示 {nodes.length}/{graph.nodes.length} 节点，{relationships.length}/
            {graph.relationships.length} 关系
          </span>
        )}
      </div>
      <svg
        ref={svgRef}
        className="kb-graph"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="文档知识图谱"
      >
        {relationships.map((rel) => {
          if (!visibleNodeIds.has(rel.source_node_id) || !visibleNodeIds.has(rel.target_node_id)) {
            return null;
          }
          const from = positions.get(rel.source_node_id);
          const to = positions.get(rel.target_node_id);
          if (!from || !to) return null;
          const active =
            selectedNodeId === rel.source_node_id || selectedNodeId === rel.target_node_id;
          return (
            <line
              key={rel.relationship_id}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              className={active ? "kb-graph-edge active" : "kb-graph-edge"}
            />
          );
        })}
        {nodes.map((node) => {
          if (!visibleNodeIds.has(node.node_id)) return null;
          const point = positions.get(node.node_id);
          if (!point) return null;
          const fill = NODE_COLORS[node.node_type] ?? NODE_COLORS.other;
          const label = node.name.length > 16 ? `${node.name.slice(0, 16)}…` : node.name;
          const selected = selectedNodeId === node.node_id;
          return (
            <g
              key={node.node_id}
              transform={`translate(${point.x},${point.y})`}
              style={{ cursor: "grab" }}
              onPointerDown={(event) => onPointerDown(node.node_id, event)}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
            >
              <circle
                r={selected ? 20 : 16}
                fill={fill}
                opacity="0.95"
                stroke={selected ? "#1c241c" : "transparent"}
                strokeWidth={selected ? 2.5 : 0}
              />
              <title>{`${node.node_type}: ${node.name}`}</title>
              <text y="34" textAnchor="middle" className="kb-graph-label">
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="kb-legend row">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <span key={type} className="chip" style={{ borderColor: color }}>
            <span className="kb-dot" style={{ background: color }} />
            {type}
          </span>
        ))}
      </div>
    </div>
  );
}

function HitTestingPanel({
  docId,
  segments,
}: {
  docId: string;
  segments: DocumentSegment[];
}) {
  const [question, setQuestion] = useState(HIT_SUGGESTIONS[0]);
  const [topK, setTopK] = useState(5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResearchResponse | null>(null);

  const segmentById = useMemo(() => {
    const map = new Map<string, DocumentSegment>();
    for (const segment of segments) map.set(segment.segment_id, segment);
    return map;
  }, [segments]);

  async function onTest(event?: FormEvent) {
    event?.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.researchPreview(docId, question.trim(), topK));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <p className="muted">
        对齐 Dify「召回测试」：对当前文档跑混合检索，检查切片命中、结构化指标与图谱路径。
      </p>
      <form className="stack" onSubmit={(event) => void onTest(event)}>
        <label className="field">
          <span>测试问题</span>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={3}
          />
        </label>
        <div className="row">
          {HIT_SUGGESTIONS.map((item) => (
            <button key={item} type="button" onClick={() => setQuestion(item)}>
              {item}
            </button>
          ))}
        </div>
        <div className="row">
          <label className="field" style={{ maxWidth: 140 }}>
            <span>Top K</span>
            <select value={topK} onChange={(event) => setTopK(Number(event.target.value))}>
              {[3, 5, 8, 10].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "检索中…" : "测试召回"}
          </button>
        </div>
      </form>

      {error && <div className="error-banner">{error}</div>}

      {result && (
        <div className="stack">
          <div className="row">
            {result.query_analysis?.intent && (
              <span className="chip">intent: {result.query_analysis.intent}</span>
            )}
            {(result.query_analysis?.routes ?? []).map((route) => (
              <span key={route} className="chip">
                {route}
              </span>
            ))}
            <span className="chip">{result.hits?.length ?? 0} 切片命中</span>
            <span className="chip">{result.metrics?.length ?? 0} 指标</span>
            <span className="chip">{result.graph_paths?.length ?? 0} 图谱路径</span>
          </div>

          {result.fusion_summary?.summary && (
            <div className="panel fusion-panel" style={{ boxShadow: "none" }}>
              <strong>融合摘要</strong>
              <p className="fusion-summary">{result.fusion_summary.summary}</p>
            </div>
          )}

          {(result.metrics?.length ?? 0) > 0 && (
            <div className="stack">
              <strong>结构化指标</strong>
              {result.metrics!.map((metric, index) => (
                <div key={`${metric.metric_key}-${metric.period}-${index}`} className="kb-segment">
                  <div className="row">
                    <strong>{metric.metric_key}</strong>
                    <span className="chip">{metric.period}</span>
                    <span className="chip good">{String(metric.value)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="stack">
            <strong>召回切片</strong>
            {(result.hits ?? []).length === 0 && <p className="muted">无向量/混合切片命中。</p>}
            {(result.hits ?? []).map((hit, index) => {
              const full = segmentById.get(hit.segment_id);
              const section = String(full?.metadata?.section_type ?? "");
              return (
                <article key={`${hit.segment_id}-${index}`} className="kb-segment">
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <div className="row">
                      <strong>Hit {String(index + 1).padStart(2, "0")}</strong>
                      <span className="chip good">score {hit.score.toFixed(4)}</span>
                      {section && <span className="chip">{section}</span>}
                      <span className="chip muted-chip">{hit.segment_id.slice(0, 10)}…</span>
                    </div>
                  </div>
                  <p className="kb-segment-body">{hit.content || full?.content || "—"}</p>
                </article>
              );
            })}
          </div>

          {(result.graph_paths?.length ?? 0) > 0 && (
            <div className="stack">
              <strong>图谱路径</strong>
              {result.graph_paths!.map((path) => (
                <div key={path.path_id} className="kb-segment">
                  <div className="row">
                    <strong>{path.path_id}</strong>
                    <span className="chip">score {path.score.toFixed(3)}</span>
                  </div>
                  <p className="kb-segment-body">{path.summary}</p>
                </div>
              ))}
            </div>
          )}

          {(result.warnings?.length ?? 0) > 0 && (
            <div className="stack">
              <strong>警告</strong>
              {result.warnings!.map((warning) => (
                <p key={warning} className="muted">
                  {warning}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function selectedNodeRelations(
  graph: DocumentKnowledgeGraph,
  nodeId: string | null,
): KnowledgeGraphRelationship[] {
  if (!nodeId) return [];
  return graph.relationships.filter(
    (rel) => rel.source_node_id === nodeId || rel.target_node_id === nodeId,
  );
}

export function KnowledgeBasePanel({
  documents,
  servingDocIds,
  initialDocId,
  onOpenResearch,
}: {
  documents: DocumentRecord[];
  servingDocIds: Set<string>;
  initialDocId?: string;
  onOpenResearch?: (docId: string) => void;
}) {
  const [view, setView] = useState<KbView>("library");
  const [detailTab, setDetailTab] = useState<DetailTab>("segments");
  const [query, setQuery] = useState("");
  const [selectedDocId, setSelectedDocId] = useState(initialDocId ?? "");
  const [segments, setSegments] = useState<DocumentSegment[]>([]);
  const [graph, setGraph] = useState<DocumentKnowledgeGraph | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [segmentQuery, setSegmentQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const libraryDocs = useMemo(() => {
    const q = query.trim().toLowerCase();
    return documents
      .filter(isWorkbenchDoc)
      .filter((doc) => {
        if (!q) return true;
        const hay = [
          doc.filename,
          doc.doc_id,
          doc.metadata.company ?? "",
          doc.metadata.doc_type ?? "",
          String(doc.metadata.year ?? ""),
        ]
          .join(" ")
          .toLowerCase();
        return hay.includes(q);
      })
      .sort((a, b) => {
        const ay = a.metadata.year ?? 0;
        const by = b.metadata.year ?? 0;
        if (by !== ay) return by - ay;
        return (b.segment_count ?? 0) - (a.segment_count ?? 0);
      });
  }, [documents, query]);

  const selectedDoc = useMemo(
    () => documents.find((item) => item.doc_id === selectedDocId) ?? null,
    [documents, selectedDocId],
  );

  const filteredSegments = useMemo(() => {
    const q = segmentQuery.trim().toLowerCase();
    if (!q) return segments;
    return segments.filter((segment) => {
      const section = String(segment.metadata?.section_type ?? "");
      const keywords = (segment.keywords ?? []).join(" ");
      return `${segment.content} ${section} ${keywords}`.toLowerCase().includes(q);
    });
  }, [segments, segmentQuery]);

  const pageCount = Math.max(1, Math.ceil(filteredSegments.length / pageSize));
  const pageSegments = filteredSegments.slice((page - 1) * pageSize, page * pageSize);

  const stats = useMemo(() => {
    const lengths = segments.map((item) => item.content.length);
    const totalChars = lengths.reduce((sum, n) => sum + n, 0);
    const avg = lengths.length ? Math.round(totalChars / lengths.length) : 0;
    const sectionTypes = new Set(
      segments
        .map((item) => String(item.metadata?.section_type ?? ""))
        .filter(Boolean),
    );
    return {
      count: segments.length,
      avgLength: avg,
      totalChars,
      sectionTypes: sectionTypes.size,
      nodeCount: graph?.nodes.length ?? 0,
      edgeCount: graph?.relationships.length ?? 0,
    };
  }, [segments, graph]);

  const selectedNode = useMemo(
    () => graph?.nodes.find((node) => node.node_id === selectedNodeId) ?? null,
    [graph, selectedNodeId],
  );
  const selectedRels = useMemo(
    () => (graph ? selectedNodeRelations(graph, selectedNodeId) : []),
    [graph, selectedNodeId],
  );

  useEffect(() => {
    if (view !== "detail" || !selectedDocId) return;
    let cancelled = false;
    setBusy(true);
    setError(null);
    setPage(1);
    setSelectedSegmentId(null);
    setSelectedNodeId(null);
    void Promise.all([
      api.listSegments(selectedDocId),
      api.getDocumentKnowledgeGraph(selectedDocId).catch(() => null),
    ])
      .then(([nextSegments, nextGraph]) => {
        if (cancelled) return;
        setSegments(nextSegments);
        setGraph(nextGraph);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setSegments([]);
        setGraph(null);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [view, selectedDocId]);

  function openDoc(docId: string) {
    setSelectedDocId(docId);
    setView("detail");
    setDetailTab("segments");
  }

  return (
    <section className="panel stack kb-panel">
      <div className="row kb-header">
        <div>
          <h2>知识库</h2>
          <p className="muted">
            对齐 Dify：知识源卡片 → 文档切片 → 召回测试 → 知识图谱。
          </p>
        </div>
        {view === "detail" ? (
          <button type="button" className="primary" onClick={() => setView("library")}>
            ← 返回知识库
          </button>
        ) : (
          <span className="chip">{libraryDocs.length} 个知识源</span>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}

      {view === "library" && (
        <>
          <div className="row">
            <label className="field" style={{ minWidth: 280 }}>
              <span>搜索知识库</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="公司 / 年份 / 文件名 / doc_id"
              />
            </label>
          </div>
          <div className="kb-card-grid">
            {libraryDocs.length === 0 && <p className="muted">暂无可用文档。请先上传或 Serving 入库。</p>}
            {libraryDocs.map((doc) => (
              <button
                key={doc.doc_id}
                type="button"
                className="kb-card"
                onClick={() => openDoc(doc.doc_id)}
              >
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <strong>{doc.metadata.company || doc.filename}</strong>
                  <span className={statusChip(doc.status)}>
                    {doc.status === "completed" ? "已启用" : doc.status}
                  </span>
                </div>
                <p className="muted kb-card-desc">{doc.filename}</p>
                <div className="row">
                  {doc.metadata.year != null && <span className="chip">{doc.metadata.year}</span>}
                  {doc.metadata.doc_type && <span className="chip">{doc.metadata.doc_type}</span>}
                  {doc.metadata.industry && <span className="chip">{doc.metadata.industry}</span>}
                  {servingDocIds.has(doc.doc_id) && <span className="chip good">Serving</span>}
                </div>
                <div className="row kb-card-meta">
                  <span className="muted">{doc.segment_count} 分段</span>
                  <span className="muted">{doc.doc_id.slice(0, 8)}…</span>
                  <span className="muted">更新 {formatWhen(doc.updated_at)}</span>
                </div>
              </button>
            ))}
          </div>
        </>
      )}

      {view === "detail" && selectedDoc && (
        <div className="kb-detail-shell">
          <nav className="kb-subnav stack">
            <div className="kb-subnav-brand">
              <strong>{selectedDoc.metadata.company || selectedDoc.filename}</strong>
              <span className="muted">
                {[selectedDoc.metadata.doc_type || "annual_report", selectedDoc.metadata.year]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </div>
            {(
              [
                ["segments", "文档"],
                ["hit", "召回测试"],
                ["graph", "知识图谱"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={detailTab === id ? "kb-subnav-item active" : "kb-subnav-item"}
                onClick={() => setDetailTab(id)}
              >
                {label}
              </button>
            ))}
            <div className="kb-subnav-foot muted">
              <div>文档 1</div>
              <div>{stats.count} 分段</div>
              <div>{stats.nodeCount} 图谱节点</div>
            </div>
          </nav>

          <div className="kb-detail">
            <div className="kb-detail-main stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div>
                  <h3 style={{ margin: 0 }}>
                    {selectedDoc.filename}{" "}
                    <span className={statusChip(selectedDoc.status)}>
                      {selectedDoc.status === "completed" ? "已启用" : selectedDoc.status}
                    </span>
                  </h3>
                  <p className="muted">
                    {detailTab === "segments" && "浏览切片后的文本块"}
                    {detailTab === "hit" && "测试该知识源的检索召回"}
                    {detailTab === "graph" && "查看完整知识图谱（可拖拽节点）"}
                  </p>
                </div>
                <div className="row">
                  {onOpenResearch && (
                    <button
                      type="button"
                      className="primary"
                      onClick={() => onOpenResearch(selectedDoc.doc_id)}
                    >
                      去研究问答
                    </button>
                  )}
                </div>
              </div>

              {busy && detailTab !== "hit" && <p className="muted">正在加载切片 / 图谱…</p>}

              {detailTab === "segments" && (
                <>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <strong>{filteredSegments.length} 分段</strong>
                    <div className="row">
                      <input
                        value={segmentQuery}
                        onChange={(event) => {
                          setSegmentQuery(event.target.value);
                          setPage(1);
                        }}
                        placeholder="搜索分段内容 / 关键词 / section"
                        style={{ minWidth: 240 }}
                      />
                      <select
                        value={pageSize}
                        onChange={(event) => {
                          setPageSize(Number(event.target.value));
                          setPage(1);
                        }}
                      >
                        {[10, 25, 50].map((size) => (
                          <option key={size} value={size}>
                            {size} / 页
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="kb-segment-list">
                    {pageSegments.map((segment, index) => {
                      const globalIndex = (page - 1) * pageSize + index + 1;
                      const section = String(segment.metadata?.section_type ?? "");
                      const active = selectedSegmentId === segment.segment_id;
                      return (
                        <article
                          key={segment.segment_id}
                          className={`kb-segment ${active ? "active" : ""}`}
                          onClick={() =>
                            setSelectedSegmentId((current) =>
                              current === segment.segment_id ? null : segment.segment_id,
                            )
                          }
                        >
                          <div className="row" style={{ justifyContent: "space-between" }}>
                            <div className="row">
                              <strong>分段 {String(globalIndex).padStart(2, "0")}</strong>
                              <span className="chip">{segment.content.length} 字符</span>
                              {section && <span className="chip">{section}</span>}
                              <span className="chip muted-chip">#{segment.position}</span>
                            </div>
                            <span className="chip good">已启用</span>
                          </div>
                          <p className="kb-segment-body">
                            {active ? segment.content : segmentPreview(segment.content)}
                          </p>
                          {(segment.keywords?.length ?? 0) > 0 && (
                            <div className="row">
                              {segment.keywords!.slice(0, 8).map((keyword) => (
                                <span key={keyword} className="chip">
                                  #{keyword}
                                </span>
                              ))}
                            </div>
                          )}
                        </article>
                      );
                    })}
                    {pageSegments.length === 0 && !busy && (
                      <p className="muted">没有匹配的分段。</p>
                    )}
                  </div>

                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span className="muted">
                      第 {page} / {pageCount} 页
                    </span>
                    <div className="row">
                      <button
                        type="button"
                        disabled={page <= 1}
                        onClick={() => setPage((current) => Math.max(1, current - 1))}
                      >
                        上一页
                      </button>
                      <button
                        type="button"
                        disabled={page >= pageCount}
                        onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                      >
                        下一页
                      </button>
                    </div>
                  </div>
                </>
              )}

              {detailTab === "hit" && (
                <HitTestingPanel docId={selectedDoc.doc_id} segments={segments} />
              )}

              {detailTab === "graph" && (
                <div className="stack">
                  <div className="row">
                    <span className="chip">{stats.nodeCount} 节点</span>
                    <span className="chip">{stats.edgeCount} 关系</span>
                    {graph?.company_id && <span className="chip">{graph.company_id}</span>}
                  </div>
                  {graph ? (
                    <KnowledgeGraphCanvas
                      graph={graph}
                      selectedNodeId={selectedNodeId}
                      onSelectNode={setSelectedNodeId}
                    />
                  ) : (
                    <p className="muted">暂无图谱数据。</p>
                  )}
                </div>
              )}
            </div>

            <aside className="kb-detail-side stack">
              <div className="panel stack" style={{ boxShadow: "none" }}>
                <h3>文档信息</h3>
                <div className="kb-meta-grid">
                  <span className="muted">原始文件</span>
                  <span>{selectedDoc.filename}</span>
                  <span className="muted">公司</span>
                  <span>{selectedDoc.metadata.company || "—"}</span>
                  <span className="muted">年份</span>
                  <span>{selectedDoc.metadata.year ?? "—"}</span>
                  <span className="muted">类型</span>
                  <span>{selectedDoc.metadata.doc_type || "annual_report"}</span>
                  <span className="muted">doc_id</span>
                  <span className="mono">{selectedDoc.doc_id}</span>
                  <span className="muted">更新时间</span>
                  <span>{formatWhen(selectedDoc.updated_at)}</span>
                </div>
              </div>
              <div className="panel stack" style={{ boxShadow: "none" }}>
                <h3>技术参数</h3>
                <div className="kb-meta-grid">
                  <span className="muted">分段数量</span>
                  <span>{stats.count}</span>
                  <span className="muted">平均段落长度</span>
                  <span>{stats.avgLength} 字符</span>
                  <span className="muted">总字符数</span>
                  <span>{stats.totalChars.toLocaleString("zh-CN")}</span>
                  <span className="muted">section 类型数</span>
                  <span>{stats.sectionTypes}</span>
                  <span className="muted">图谱节点</span>
                  <span>{stats.nodeCount}</span>
                  <span className="muted">图谱关系</span>
                  <span>{stats.edgeCount}</span>
                </div>
              </div>
              {detailTab === "graph" && selectedNode && (
                <div className="panel stack" style={{ boxShadow: "none" }}>
                  <h3>选中节点</h3>
                  <div className="kb-meta-grid">
                    <span className="muted">名称</span>
                    <span>{selectedNode.name}</span>
                    <span className="muted">类型</span>
                    <span>{selectedNode.node_type}</span>
                    <span className="muted">node_id</span>
                    <span className="mono">{selectedNode.node_id}</span>
                    <span className="muted">关联边</span>
                    <span>{selectedRels.length}</span>
                  </div>
                  {selectedRels.slice(0, 8).map((rel) => (
                    <p key={rel.relationship_id} className="muted">
                      {rel.relationship_type}: {rel.source_node_id.slice(0, 8)}→
                      {rel.target_node_id.slice(0, 8)}
                      {rel.evidence_text ? ` · ${segmentPreview(rel.evidence_text, 80)}` : ""}
                    </p>
                  ))}
                </div>
              )}
            </aside>
          </div>
        </div>
      )}
    </section>
  );
}
