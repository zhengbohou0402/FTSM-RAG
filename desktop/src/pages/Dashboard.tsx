import { useEffect, useState, useCallback } from "react";
import { Button, Typography, Space, Progress } from "antd";
import { ReloadOutlined, ArrowLeftOutlined, SettingOutlined, AppstoreOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { KnowledgeStats, CacheStats, TrainingStatus, SchedulerStatus } from "../api/client";
import StatsCard from "../components/StatsCard";
import StatusBadge from "../components/StatusBadge";

const { Text } = Typography;

function fmtPast(iso: string | null): string {
  if (!iso) return "—";
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return Math.floor(diff / 60) + "m ago";
  if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
  return Math.floor(diff / 86400) + "d ago";
}

function fmtFuture(iso: string | null): string {
  if (!iso) return "—";
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  if (diff <= 0) return "due now";
  if (diff < 3600) return "in " + Math.ceil(diff / 60) + "m";
  if (diff < 86400) return "in " + Math.ceil(diff / 3600) + "h";
  return "in " + Math.ceil(diff / 86400) + "d";
}

export default function Dashboard() {
  const [kb, setKb] = useState<KnowledgeStats | null>(null);
  const [cache, setCache] = useState<CacheStats | null>(null);
  const [training, setTraining] = useState<TrainingStatus | null>(null);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [convCount, setConvCount] = useState<number>(0);
  const [updatedAt, setUpdatedAt] = useState("");

  const loadAll = useCallback(async () => {
    try {
      const [kbData, cacheData, trainData, schedData, convs] = await Promise.all([
        api.knowledge.stats(),
        api.cache.stats(),
        api.training.status(),
        api.scheduler.status(),
        api.conversations.list(),
      ]);
      setKb(kbData);
      setCache(cacheData);
      setTraining(trainData);
      setScheduler(schedData);
      setConvCount(convs.items.length);
    } catch {
      // ignore
    }
    setUpdatedAt(new Date().toLocaleTimeString());
  }, []);

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 30000);
    return () => clearInterval(interval);
  }, [loadAll]);

  const trainStatus: "running" | "idle" | "error" | "success" =
    training?.running ? "running" :
    training?.pending ? "running" :
    training?.last_error ? "error" :
    training?.last_result === "success" ? "success" : "idle";

  return (
    <div className="dash-shell">
      <div className="dash-header">
        <div>
          <Text type="secondary" style={{ letterSpacing: 1, fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>
            FTSM-RAG
          </Text>
          <h1 style={{ margin: 0 }}>System Dashboard</h1>
          <p>Real-time metrics for knowledge base, cache and indexing.</p>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadAll}>Refresh</Button>
          <Link to="/manage"><Button icon={<AppstoreOutlined />}>Manage</Button></Link>
          <Link to="/settings"><Button icon={<SettingOutlined />}>Settings</Button></Link>
          <Link to="/"><Button icon={<ArrowLeftOutlined />}>Chat</Button></Link>
        </Space>
      </div>

      {/* Pipeline */}
      <div className="dash-section">
        <Text strong style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: "#888" }}>
          Retrieval Pipeline
        </Text>
        <div className="pipeline">
          {[
            { icon: "❓", label: "User Query", sub: "multi-query expansion" },
            { icon: "🔍", label: "Vector Search", sub: "ChromaDB k=12" },
            { icon: "📝", label: "BM25 Search", sub: "keyword k=12" },
            { icon: "⚖️", label: "RRF Fusion", sub: "merge & re-rank" },
            { icon: "🏆", label: "Reranker", sub: "gte-rerank-v2 top-6" },
            { icon: "🤖", label: "LLM Answer", sub: "Qwen" },
          ].map((step, idx) => (
            <span key={idx} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div className="pipeline-step">
                <div className="pipeline-step-icon">{step.icon}</div>
                <div className="pipeline-step-label">{step.label}</div>
                <div className="pipeline-step-sub">{step.sub}</div>
              </div>
              {idx < 5 && <span className="pipeline-arrow">›</span>}
            </span>
          ))}
        </div>
      </div>

      {/* Knowledge Base */}
      <div className="dash-section">
        <Text strong style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: "#888" }}>
          Knowledge Base
        </Text>
        <div className="stats-grid">
          <StatsCard label="Documents" value={kb?.document_count ?? "—"} sub="uploaded files" accent="blue" />
          <StatsCard label="Vector Chunks" value={kb?.total_chunks ?? "—"} sub="indexed in Chroma" accent="purple" />
          <StatsCard label="Manifest Records" value={kb?.manifest_records ?? "—"} sub="processed docs" accent="blue" />
          <StatsCard
            label="Last Indexed"
            value={fmtPast(kb?.last_indexed ?? null)}
            sub={kb?.last_indexed ? new Date(kb.last_indexed).toLocaleString() : undefined}
          />
        </div>
      </div>

      {/* Semantic Cache */}
      <div className="dash-section">
        <Text strong style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: "#888" }}>
          Semantic Cache
        </Text>
        <div style={{ background: "#fff", padding: "12px 16px", borderRadius: 12, marginBottom: 12, border: "1px solid #e5e7eb" }}>
          <Text strong style={{ display: "block", marginBottom: 8 }}>Cache Hit Rate (since last restart)</Text>
          <Progress percent={Math.round((cache?.hit_rate || 0) * 100)} />
        </div>
        <div className="stats-grid">
          <StatsCard label="Cache Hits" value={cache?.hit_count ?? "—"} sub="saved LLM calls" accent="green" />
          <StatsCard label="Cache Misses" value={cache?.miss_count ?? "—"} sub="new LLM calls" accent="amber" />
          <StatsCard label="Cached Entries" value={cache?.size ?? "—"} sub={`${cache?.valid ?? "—"} valid`} />
          <StatsCard label="Threshold" value={cache?.threshold ?? "—"} sub="cosine similarity" accent="blue" />
        </div>
      </div>

      {/* Indexing Worker */}
      <div className="dash-section">
        <Text strong style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: "#888" }}>
          Indexing Worker
        </Text>
        <div className="dash-info-card">
          <div><Text type="secondary">Status</Text><div><StatusBadge status={trainStatus} /></div></div>
          <div><Text type="secondary">Last Result</Text><div><Text strong>{training?.last_result || "—"}</Text></div></div>
          <div><Text type="secondary">Last Error</Text><div><Text type="danger" style={{ fontSize: 12 }}>{training?.last_error || "—"}</Text></div></div>
        </div>
      </div>

      {/* Conversations & Scheduler */}
      <div className="dash-section">
        <Text strong style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: "#888" }}>
          Conversations & Scheduler
        </Text>
        <div className="stats-grid">
          <StatsCard label="Conversations" value={convCount} sub="stored on disk" accent="blue" />
          <StatsCard
            label="Crawler Scheduler"
            value={scheduler?.enabled ? "Enabled" : "Disabled"}
            sub={scheduler?.enabled ? `every ${scheduler.interval_hours}h` : "frozen / disabled"}
          />
          <StatsCard
            label="Last Crawl"
            value={fmtPast(scheduler?.last_run ?? null)}
            sub={scheduler?.next_run ? `next: ${fmtFuture(scheduler.next_run)}` : "—"}
          />
        </div>
      </div>

      <div style={{ textAlign: "right", marginTop: 24 }}>
        <Text type="secondary">Last updated: {updatedAt}</Text>
      </div>
    </div>
  );
}
