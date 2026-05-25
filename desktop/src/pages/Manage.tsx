import { useEffect, useState, useCallback } from "react";
import { Upload, Button, List, Typography, Card, Space, message, Progress, Popconfirm, Empty } from "antd";
import {
  ArrowLeftOutlined,
  BulbFilled,
  BulbOutlined,
  CloudUploadOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  FileImageOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  ReloadOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Document, TrainingStatus, KnowledgeStats, CacheStats } from "../api/client";
import StatsCard from "../components/StatsCard";
import StatusBadge from "../components/StatusBadge";

const { Dragger } = Upload;
const { Text } = Typography;

interface Props {
  isDark: boolean;
  onToggleTheme: () => void;
}

function formatBytes(bytes: number): string {
  if (!bytes) return "0 KB";
  if (bytes < 1048576) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

function formatIndexed(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "-";
}

function documentIcon(name: string) {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FilePdfOutlined />;
  if (["png", "jpg", "jpeg", "webp", "gif"].includes(ext || "")) return <FileImageOutlined />;
  return <FileTextOutlined />;
}

export default function Manage({ isDark, onToggleTheme }: Props) {
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
      // keep the last visible state
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => {
      void refreshAll();
    }, 0);
    const interval = window.setInterval(() => {
      void refreshAll();
    }, 10000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(interval);
    };
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
        message.error(result.errors.map((err) => String(err)).join(", "));
      }
      if (result.saved.length > 0) {
        message.success(`Uploaded: ${result.saved.join(", ")}`);
      }
      void refreshAll();
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
      void refreshAll();
    } catch (err) {
      message.error(`Delete failed: ${err}`);
    }
  };

  const handleReindex = async () => {
    try {
      const result = await api.training.start();
      message.info(result.message);
      void refreshAll();
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
    <div className="admin-shell manage-shell">
      <div className="admin-header manage-header">
        <div>
          <Text type="secondary" className="page-kicker">FTSM-RAG</Text>
          <h1>Document Management</h1>
          <p>Review knowledge-base health, add source files, and rebuild the vector index.</p>
        </div>
        <Space wrap>
          <Button icon={isDark ? <BulbFilled /> : <BulbOutlined />} onClick={onToggleTheme}>
            {isDark ? "Light" : "Dark"}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={refreshAll}>Refresh</Button>
          <Link to="/dashboard"><Button icon={<DashboardOutlined />}>Dashboard</Button></Link>
          <Link to="/settings"><Button icon={<SettingOutlined />}>Settings</Button></Link>
          <Link to="/"><Button icon={<ArrowLeftOutlined />}>Back to Chat</Button></Link>
        </Space>
      </div>

      <section className="admin-panel manage-status-panel">
        <div className="manage-status-main">
          <Text type="secondary" className="section-kicker">Indexing Worker</Text>
          <div className="manage-status-row">
            <StatusBadge status={trainStatus} label={
              training?.running ? "Indexing in progress" :
              training?.pending ? "Queued" :
              training?.last_error ? "Indexing failed" :
              training?.last_result === "success" ? "Ready" : "Idle"
            } />
            {training?.last_error && <Text type="danger">{training.last_error}</Text>}
          </div>
        </div>
        <Button type="primary" icon={<DatabaseOutlined />} onClick={handleReindex} loading={training?.running}>
          Re-index all
        </Button>
      </section>

      <section className="admin-section manage-section">
        <Text strong className="section-kicker">Knowledge Base</Text>
        <div className="stats-grid manage-stats-grid">
          <StatsCard label="Documents" value={kb?.document_count ?? "-"} sub="source files" accent="blue" />
          <StatsCard label="Vector Chunks" value={kb?.total_chunks ?? "-"} sub="searchable segments" accent="purple" />
          <StatsCard label="Manifest Records" value={kb?.manifest_records ?? "-"} sub="indexed documents" />
          <StatsCard label="Last Indexed" value={formatIndexed(kb?.last_indexed)} />
        </div>
      </section>

      <div className="manage-grid">
        <Card className="manage-card" title="Upload Files" extra={<Text type="secondary">TXT, PDF, images</Text>}>
          <Dragger
            className="manage-upload"
            multiple
            showUploadList={false}
            beforeUpload={handleUpload}
            disabled={uploading}
            accept=".txt,.pdf,.png,.jpg,.jpeg,.webp,.gif"
          >
            <p className="ant-upload-drag-icon"><CloudUploadOutlined /></p>
            <p className="manage-upload-title">Drop files here or click to upload</p>
            <p className="manage-upload-hint">Files are saved to the knowledge folder, then the index can be rebuilt.</p>
          </Dragger>

          {cache && (
            <div className="manage-cache-card">
              <div>
                <Text strong>Semantic Cache</Text>
                <p>{cache.size} entries, {cache.valid} currently valid</p>
              </div>
              <Progress
                type="circle"
                size={62}
                percent={Math.round((cache.hit_rate || 0) * 100)}
              />
            </div>
          )}
        </Card>

        <Card
          className="manage-card manage-list-card"
          title="Knowledge Base"
          extra={
            <Space>
              <Text type="secondary">{docs.length} files</Text>
              <Button icon={<ReloadOutlined />} onClick={refreshAll}>Refresh</Button>
            </Space>
          }
        >
          <List
            className="manage-doc-list"
            dataSource={docs}
            renderItem={(doc) => (
              <List.Item className="manage-doc-item">
                <List.Item.Meta
                  avatar={<span className="manage-doc-icon">{documentIcon(doc.name)}</span>}
                  title={<span className="manage-doc-title">{doc.name}</span>}
                  description={`${formatBytes(doc.size)} - modified ${formatDate(doc.modified)}`}
                />
                <Popconfirm
                  title="Delete document?"
                  description={doc.name}
                  okText="Delete"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => handleDelete(doc.name)}
                >
                  <Button type="text" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </List.Item>
            )}
            locale={{ emptyText: <Empty description="No documents uploaded yet" /> }}
          />
        </Card>
      </div>
    </div>
  );
}
