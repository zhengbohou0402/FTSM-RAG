// === TRILINGUAL DEMO FEATURE ===
import { useState, useRef, useEffect } from "react";
import {
  Layout,
  Typography,
  Input,
  Button,
  Card,
  Row,
  Col,
  Space,
  Badge,
  Spin,
  Collapse,
  theme,
  message,
} from "antd";
import {
  GlobalOutlined,
  SendOutlined,
  SyncOutlined,
  BookOutlined,
  SearchOutlined,
  DatabaseOutlined,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import { api } from "../api/client";
import type { Message, Source } from "../api/client";
import { parseAssistantMessage } from "../utils/messageParser";

const { Content } = Layout;
const { Text } = Typography;
const { TextArea } = Input;

function guessThinkingType(text: string): string {
  const lower = text.toLowerCase();
  if (lower.includes("search") || lower.includes("knowledge")) return "searching";
  if (lower.includes("cache")) return "cache";
  return "";
}

function processLabel(text: string): string {
  const kind = guessThinkingType(text);
  if (kind === "searching") return "Searching knowledge base";
  if (kind === "cache") return "Answering from cache";
  return text.replace(/\.+$/, "");
}

interface ColumnSourcesProps {
  sources: Source[];
  token: any;
}

function ColumnSources({ sources, token }: ColumnSourcesProps) {
  if (!sources || sources.length === 0) return null;
  return (
    <div
      style={{
        marginTop: "16px",
        paddingTop: "12px",
        borderTop: `1px dashed ${token.colorBorderSecondary}`,
      }}
    >
      <Collapse
        ghost
        size="small"
        items={[
          {
            key: "sources",
            label: (
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 600,
                  color: token.colorPrimary,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <BookOutlined /> Cited Sources ({sources.length})
              </span>
            ),
            children: (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                  maxHeight: "180px",
                  overflowY: "auto",
                }}
                className="markdown-scroll"
              >
                {sources.map((s, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "8px",
                      background: token.colorBgLayout,
                      borderRadius: token.borderRadiusOuter,
                      fontSize: "11px",
                      border: `1px solid ${token.colorBorderSecondary}`,
                    }}
                  >
                    <div
                      style={{
                        fontWeight: 600,
                        color: token.colorTextSecondary,
                        display: "flex",
                        justifyContent: "space-between",
                        marginBottom: "4px",
                        gap: "8px",
                      }}
                    >
                      <span style={{ wordBreak: "break-all" }}>
                        [{idx + 1}] {s.file.replace(/\.[^/.]+$/, "").replace(/[_-]+/g, " ")}
                      </span>
                      {s.source_type && (
                        <Badge
                          size="small"
                          status="processing"
                          text={<span style={{ fontSize: "10px", color: token.colorTextDescription }}>{s.source_type}</span>}
                        />
                      )}
                    </div>
                    {s.excerpt && (
                      <div
                        style={{
                          color: token.colorTextDescription,
                          fontStyle: "italic",
                          whiteSpace: "pre-wrap",
                          marginTop: "2px",
                        }}
                      >
                        {s.excerpt}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}

export default function TrilingualCompare() {
  const { token } = theme.useToken();
  const [baseQuery, setBaseQuery] = useState("");
  const [queries, setQueries] = useState({ zh: "", en: "", ms: "" });
  const [translating, setTranslating] = useState(false);
  const [streaming, setStreaming] = useState({ zh: false, en: false, ms: false });
  const [answers, setAnswers] = useState<{
    zh: Message | null;
    en: Message | null;
    ms: Message | null;
  }>({ zh: null, en: null, ms: null });

  // Scroll refs for columns
  const zhScrollRef = useRef<HTMLDivElement>(null);
  const enScrollRef = useRef<HTMLDivElement>(null);
  const msScrollRef = useRef<HTMLDivElement>(null);

  // Auto scroll columns to bottom as text arrives
  useEffect(() => {
    if (zhScrollRef.current) zhScrollRef.current.scrollTop = zhScrollRef.current.scrollHeight;
  }, [answers.zh]);

  useEffect(() => {
    if (enScrollRef.current) enScrollRef.current.scrollTop = enScrollRef.current.scrollHeight;
  }, [answers.en]);

  useEffect(() => {
    if (msScrollRef.current) msScrollRef.current.scrollTop = msScrollRef.current.scrollHeight;
  }, [answers.ms]);

  const handleTranslate = async () => {
    const trimmed = baseQuery.trim();
    if (!trimmed) {
      message.warning("Please enter a base query to translate first.");
      return;
    }
    setTranslating(true);
    try {
      const res = await api.translate(trimmed);
      setQueries({
        zh: res.zh || trimmed,
        en: res.en || trimmed,
        ms: res.ms || trimmed,
      });
      message.success("Successfully translated query into 3 languages!");
    } catch (err) {
      message.error(`Translation failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setTranslating(false);
    }
  };

  const handleConcurrentAsk = async () => {
    if (!queries.zh.trim() && !queries.en.trim() && !queries.ms.trim()) {
      message.warning("Please specify at least one query to run.");
      return;
    }

    setAnswers({ zh: null, en: null, ms: null });
    setStreaming({ zh: true, en: true, ms: true });

    const streamColumn = async (lang: "zh" | "en" | "ms", text: string) => {
      if (!text.trim()) {
        setStreaming((prev) => ({ ...prev, [lang]: false }));
        return;
      }

      let rawContent = "";
      try {
        const { reader } = await api.chat(text, null, lang);
        const decoder = new TextDecoder();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          rawContent += decoder.decode(value, { stream: true });
          const parsed = parseAssistantMessage(rawContent, true);

          setAnswers((prev) => ({
            ...prev,
            [lang]: parsed,
          }));
        }

        const finalParsed = parseAssistantMessage(rawContent, false);
        setAnswers((prev) => ({
          ...prev,
          [lang]: finalParsed,
        }));
      } catch (err) {
        setAnswers((prev) => ({
          ...prev,
          [lang]: {
            role: "assistant",
            content: `Error: ${err instanceof Error ? err.message : "Unknown error"}`,
          },
        }));
      } finally {
        setStreaming((prev) => ({ ...prev, [lang]: false }));
      }
    };

    void Promise.all([
      streamColumn("zh", queries.zh),
      streamColumn("en", queries.en),
      streamColumn("ms", queries.ms),
    ]);
  };

  const isAnyStreaming = streaming.zh || streaming.en || streaming.ms;

  const renderColumnContent = (lang: "zh" | "en" | "ms", title: string, badgeText: string, badgeColor: string) => {
    const msg = answers[lang];
    const isStream = streaming[lang];
    const hasThinking = msg && msg.thinking && msg.thinking.length > 0;
    const hasContent = msg && msg.content && msg.content.length > 0;
    const showThinkingPlaceholder = hasThinking && !hasContent;
    const scrollRef = lang === "zh" ? zhScrollRef : lang === "en" ? enScrollRef : msScrollRef;

    return (
      <Card
        className={`compare-card ${isStream ? "column-streaming" : msg ? "column-completed" : ""}`}
        title={
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 600 }}>{title}</span>
            <Badge color={badgeColor} text={badgeText} />
          </div>
        }
        style={{ height: "100%", display: "flex", flexDirection: "column" }}
        bodyStyle={{ flex: 1, display: "flex", flexDirection: "column", padding: "10px", overflow: "hidden" }}
      >
        <div
          ref={scrollRef}
          style={{ flex: 1, overflowY: "auto", minHeight: "150px", maxHeight: "250px" }}
          className="markdown-scroll"
        >
          {/* Thinking process */}
          {(hasThinking || showThinkingPlaceholder) && (
            <div style={{ marginBottom: hasContent ? "12px" : "0" }}>
              <span
                style={{
                  display: "inline-flex",
                  flexWrap: "wrap",
                  gap: "6px",
                  padding: "4px 8px",
                  background: token.colorBgLayout,
                  borderRadius: "16px",
                  fontSize: "11px",
                  border: `1px solid ${token.colorBorderSecondary}`,
                }}
              >
                {msg.thinking!.map((t, i) => (
                  <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                    {guessThinkingType(t) === "searching" && <SearchOutlined style={{ color: token.colorPrimary }} />}
                    {guessThinkingType(t) === "cache" && <DatabaseOutlined style={{ color: "#52c41a" }} />}
                    <span style={{ color: token.colorTextDescription }}>{processLabel(t)}</span>
                    {i < msg.thinking!.length - 1 && <span style={{ opacity: 0.3 }}>/</span>}
                  </span>
                ))}
              </span>
            </div>
          )}

          {/* Assistant content */}
          {hasContent ? (
            <div className="markdown-body" style={{ fontSize: "13px", lineHeight: "1.6" }}>
              <ReactMarkdown>{msg.content}</ReactMarkdown>
            </div>
          ) : isStream ? (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "12px 0", color: token.colorTextDescription }}>
              <Spin size="small" />
              <span>Generating response...</span>
            </div>
          ) : (
            <div style={{ padding: "40px 0", textAlign: "center", color: token.colorTextDescription }}>
              Waiting for query...
            </div>
          )}
        </div>

        {/* Citations list */}
        {msg && msg.sources && msg.sources.length > 0 && (
          <ColumnSources sources={msg.sources} token={token} />
        )}
      </Card>
    );
  };

  return (
    <Content className="compare-container">
      {/* Scope specific styles */}
      <style dangerouslySetInnerHTML={{ __html: `
        .compare-container {
          padding: 12px;
          height: 100%;
          overflow-y: auto;
          box-sizing: border-box;
        }
        .compare-card {
          backdrop-filter: blur(10px);
          background: ${token.colorBgContainer};
          border: 1px solid ${token.colorBorderSecondary};
          transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }
        .compare-card:hover {
          box-shadow: 0 4px 16px rgba(0,0,0,0.08);
          transform: translateY(-2px);
        }
        .column-streaming {
          border-color: ${token.colorPrimary} !important;
          box-shadow: 0 0 12px rgba(46, 109, 164, 0.15);
        }
        .column-completed {
          border-color: #52c41a !important;
        }
        .markdown-scroll::-webkit-scrollbar {
          width: 5px;
        }
        .markdown-scroll::-webkit-scrollbar-track {
          background: transparent;
        }
        .markdown-scroll::-webkit-scrollbar-thumb {
          background: ${token.colorBorder};
          border-radius: 3px;
        }
        .markdown-scroll::-webkit-scrollbar-thumb:hover {
          background: ${token.colorTextDescription};
        }
      `}} />

      {/* Header Banner */}
      <div
        style={{
          padding: "8px 16px",
          background: token.colorBgContainer,
          border: `1px solid ${token.colorBorderSecondary}`,
          borderRadius: token.borderRadius,
          marginBottom: "8px",
          display: "flex",
          alignItems: "center",
          gap: "8px"
        }}
      >
        <GlobalOutlined style={{ color: token.colorPrimary, fontSize: "16px" }} />
        <Text strong style={{ fontSize: "14px", margin: 0 }}>
          Trilingual Response Comparison (三语对比演示)
        </Text>
      </div>

      {/* Control Panel Card */}
      <Card className="compare-card" style={{ marginBottom: "8px" }} bodyStyle={{ padding: "8px 12px" }}>
        <Space direction="vertical" size="small" style={{ width: "100%" }}>
          <div>
            <Text strong style={{ fontSize: "13px" }}>1. Enter Base Question (输入基本问题)</Text>
            <TextArea
              value={baseQuery}
              onChange={(e) => setBaseQuery(e.target.value)}
              placeholder="Enter a question (e.g. When is the first semester final exam?)"
              autoSize={{ minRows: 1, maxRows: 2 }}
              disabled={translating || isAnyStreaming}
              style={{ marginTop: "4px" }}
            />
          </div>

          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <Button
              icon={<SyncOutlined spin={translating} />}
              onClick={handleTranslate}
              loading={translating}
              disabled={isAnyStreaming || !baseQuery.trim()}
            >
              Auto-Translate (自动翻译成三语)
            </Button>
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleConcurrentAsk}
              disabled={translating || isAnyStreaming}
              style={{
                background: `linear-gradient(90deg, ${token.colorPrimary} 0%, #1d39c4 100%)`,
                borderColor: "transparent",
              }}
            >
              Concurrent Ask (三语同时提问)
            </Button>
          </div>

          {/* Edit queries panel */}
          <Collapse
            size="small"
            items={[
              {
                key: "queries",
                label: <span style={{ fontSize: "12px" }}>2. Review / Edit Trilingual Queries (查看及编辑各语言问题)</span>,
                children: (
                  <Row gutter={16}>
                    <Col xs={24} md={8}>
                      <div style={{ marginBottom: "8px" }}>
                        <Badge color="#1890ff" text="Chinese Query (中文)" />
                      </div>
                      <TextArea
                        value={queries.zh}
                        onChange={(e) => setQueries((prev) => ({ ...prev, zh: e.target.value }))}
                        placeholder="Chinese query text..."
                        autoSize={{ minRows: 2, maxRows: 3 }}
                        disabled={translating || isAnyStreaming}
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <div style={{ marginBottom: "8px" }}>
                        <Badge color="#2e6da4" text="English Query (英文)" />
                      </div>
                      <TextArea
                        value={queries.en}
                        onChange={(e) => setQueries((prev) => ({ ...prev, en: e.target.value }))}
                        placeholder="English query text..."
                        autoSize={{ minRows: 2, maxRows: 3 }}
                        disabled={translating || isAnyStreaming}
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <div style={{ marginBottom: "8px" }}>
                        <Badge color="#fa8c16" text="Malay Query (马来文)" />
                      </div>
                      <TextArea
                        value={queries.ms}
                        onChange={(e) => setQueries((prev) => ({ ...prev, ms: e.target.value }))}
                        placeholder="Malay query text..."
                        autoSize={{ minRows: 2, maxRows: 3 }}
                        disabled={translating || isAnyStreaming}
                      />
                    </Col>
                  </Row>
                ),
              },
            ]}
          />
        </Space>
      </Card>

      {/* Side-by-side Response Columns */}
      <Row gutter={[12, 12]} style={{ minHeight: "220px" }}>
        <Col xs={24} md={8}>
          {renderColumnContent("zh", "Simplified Chinese (中文)", "Chinese", "#1890ff")}
        </Col>
        <Col xs={24} md={8}>
          {renderColumnContent("en", "English Response (英文)", "English", "#2e6da4")}
        </Col>
        <Col xs={24} md={8}>
          {renderColumnContent("ms", "Malay Response (马来文)", "Bahasa Melayu", "#fa8c16")}
        </Col>
      </Row>
    </Content>
  );
}
// === END TRILINGUAL DEMO FEATURE ===
