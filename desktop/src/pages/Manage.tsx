import { useEffect, useState, useCallback } from "react";
import { Upload, Button, List, Typography, Card, Space, message, Progress } from "antd";
import { InboxOutlined, DeleteOutlined, ReloadOutlined, ArrowLeftOutlined, DashboardOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Document, TrainingStatus, KnowledgeStats, CacheStats } from "../api/client";
import StatsCard from "../components/StatsCard";
import StatusBadge from "../components/StatusBadge";

const { Dragger } = Upload;
const { Text } = Typography;

export default function Manage() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [training, setTraining] = useState<TrainingStatus | null>(null);
  const [kb, setKb] = useState<KnowledgeStats | null>(null);
  const [cache, setCache] = useState<CacheStats | null>(null);
  const [uploading, setUploading] = useState(false);

  const refreshAll = useCallback(async () => {
    try {
      const [d, t, k, c] = await Promise.all([
        api.documents.list(),
        api.training.status(),
        api.knowledge.stats(),
        api.cache.stats(),
      ]);
      setDocs(d.documents);
      setTraining(t);
      setKb(k);
      setCache(c);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshAll, 10000);
    return () => clearInterval(interval);
  }, [refreshAll]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const fileList = {
        0: file,
        length: 1,
        item: (idx: number) => (idx === 0 ? file : null),
        [Symbol.iterator]: function* () { yield file; },
      } as unknown as FileList;
      const result = await api.documents.upload(fileList);
      if (result.errors.length > 0) {
        message.error(result.errors.join(", "));
      }
      if (result.saved.length > 0) {
        message.success(`Uploaded: ${result.saved.join(", ")}`);
      }
      refreshAll();
    } catch (err) {
      message.error(`Upload failed: ${err}`);
    } finally {
      setUploading(false);
    }
    return false;
  };

  const handleDelete = async (filename: string) => {
    try {
      await api.documents.delete(filename);
      message.success(`Deleted: ${filename}`);
      refreshAll();
    } catch (err) {
      message.error(`Delete failed: ${err}`);
    }
  };

  const handleReindex = async () => {
    try {
      const result = await api.training.start();
      message.info(result.message);
      refreshAll();
    } catch (err) {
      message.error(`Re-index failed: ${err}`);
    }
  };

  const trainStatus: "running" | "idle" | "error" | "success" =
    training?.running ? "running" :
    training?.pending ? "running" :
    training?.last_error ? "error" :
    training?.last_result === "success" ? "success" : "idle";

  return (
    <div className="manage-shell">
      <div className="manage-header">
        <div>
          <Text type="secondary" style={{ letterSpacing: 1, fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>
            FTSM-RAG
          </Text>
          <h1>Document Management</h1>
          <p>Upload, re-index, and remove knowledge-base files.</p>
        </div>
        <Space>
          <Link to="/dashboard"><Button icon={<DashboardOutlined />}>Dashboard</Button></Link>
          <Link to="/settings"><Button>Settings</Button></Link>
          <Link to="/"><Button icon={<ArrowLeftOutlined />}>Back to Chat</Button></Link>
        </Space>
      </div>

      {training && (
        <div className="index-status-bar">
          <StatusBadge status={trainStatus} label={
            training.running ? "Indexing..." :
            training.pending ? "Queued" :
            training.last_error ? `Error: ${training.last_error}` :
            training.last_result === "success" ? "Idle" : "Idle"
          } />
        </div>
      )}

      {kb && (
        <div style={{ marginBottom: 20 }}>
          <Text strong style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: "#888" }}>
            Knowledge Base
          </Text>
          <div className="stats-grid">
            <StatsCard label="Documents" value={kb.document_count} accent="blue" />
            <StatsCard label="Vector Chunks" value={kb.total_chunks} accent="purple" />
            <StatsCard label="Manifest Records" value={kb.manifest_records} />
            <StatsCard label="Last Indexed" value={kb.last_indexed ? new Date(kb.last_indexed).toLocaleString() : "—"} />
          </div>
        </div>
      )}

      {cache && (
        <div style={{ marginBottom: 20 }}>
          <Text strong style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: "#888" }}>
            Semantic Cache
          </Text>
          <Card size="small" style={{ marginBottom: 12 }}>
            <Text strong>Cache Hit Rate</Text>
            <Progress percent={Math.round((cache.hit_rate || 0) * 100)} />
          </Card>
          <div className="stats-grid">
            <StatsCard label="Cache Hits" value={cache.hit_count} accent="green" />
            <StatsCard label="Cache Misses" value={cache.miss_count} accent="amber" />
            <StatsCard label="Cached Entries" value={cache.size} />
          </div>
        </div>
      )}

      <div className="manage-grid">
        <Card title="Upload Files" extra={<Text type="secondary">TXT, PDF, PNG, JPG, WEBP, GIF</Text>}>
          <Dragger
            multiple
            showUploadList={false}
            beforeUpload={handleUpload}
            disabled={uploading}
            accept=".txt,.pdf,.png,.jpg,.jpeg,.webp,.gif"
          >
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p>Click or drag files to upload</p>
          </Dragger>
        </Card>

        <Card
          title="Knowledge Base"
          extra={
            <Space>
              <Text type="secondary">{docs.length} files</Text>
              <Button icon={<ReloadOutlined />} onClick={refreshAll}>Refresh</Button>
              <Button onClick={handleReindex}>Re-index all</Button>
            </Space>
          }
        >
          <List
            dataSource={docs}
            renderItem={(doc) => (
              <List.Item
                actions={[
                  <Button
                    key="delete"
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => handleDelete(doc.name)}
                  />,
                ]}
              >
                <List.Item.Meta
                  title={doc.name}
                  description={`${(doc.size / 1048576).toFixed(1)} MB - ${new Date(doc.modified * 1000).toLocaleDateString()}`}
                />
              </List.Item>
            )}
            locale={{ emptyText: "No documents uploaded yet" }}
          />
        </Card>
      </div>
    </div>
  );
}
