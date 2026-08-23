import { useState } from "react";
import type { ComponentPropsWithoutRef } from "react";
import { Typography, Button } from "antd";
import {
  CheckOutlined,
  CopyOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Message, Source } from "../api/client";

const { Text } = Typography;

interface Props {
  message: Message;
}

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

type CodeBlockProps = ComponentPropsWithoutRef<"code"> & { inline?: boolean };

function CodeBlock({ inline, className, children, ...props }: CodeBlockProps) {
  const match = /language-(\w+)/.exec(className || "");
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(String(children).replace(/\n$/, ""));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!inline && match) {
    return (
      <div style={{ position: "relative", marginBottom: "1.2em", borderRadius: "8px", overflow: "hidden", boxShadow: "0 4px 12px rgba(0,0,0,0.1)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#2d2d2d", padding: "6px 12px", color: "#aaa", fontSize: "12px" }}>
          <span style={{ fontWeight: 600 }}>{match[1]}</span>
          <Button 
            type="text" 
            size="small" 
            icon={copied ? <CheckOutlined style={{ color: "#52c41a" }} /> : <CopyOutlined style={{ color: "#aaa" }} />} 
            onClick={handleCopy} 
            style={{ height: "20px", padding: "0 4px" }}
          >
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
        <SyntaxHighlighter
          {...props}
          style={vscDarkPlus}
          language={match[1]}
          PreTag="div"
          customStyle={{ margin: 0, borderRadius: "0 0 8px 8px", fontSize: "13px" }}
        >
          {String(children).replace(/\n$/, "")}
        </SyntaxHighlighter>
      </div>
    );
  }
  return (
    <code {...props} className={className} style={{ background: "rgba(150,150,150,0.15)", padding: "2px 6px", borderRadius: "4px", fontSize: "0.9em", color: "#d63384" }}>
      {children}
    </code>
  );
}

function sourceTone(sourceType?: string): string {
  const normalized = sourceType?.toLowerCase() ?? "";
  if (normalized.includes("official")) return "official";
  if (normalized.includes("student")) return "guide";
  if (normalized.includes("generated")) return "generated";
  return "default";
}

function sourceTitle(file: string): string {
  return file.replace(/\.[^/.]+$/, "").replace(/[_-]+/g, " ");
}

function SourcesPanel({ sources }: { sources: Source[] }) {
  const documentCount = new Set(sources.map((source) => source.file.toLowerCase())).size;

  return (
    <section className="sources-panel" aria-label="Answer sources">
      <div className="sources-panel-header">
        <div className="sources-panel-title">
          <span className="sources-panel-icon"><FileTextOutlined /></span>
          <span>Sources</span>
          <span className="sources-panel-count">{sources.length}</span>
        </div>
        <span className="sources-panel-summary">
          {documentCount} {documentCount === 1 ? "document" : "documents"}
        </span>
      </div>

      <div className="source-card-grid">
        {sources.map((source, index) => {
          const tone = sourceTone(source.source_type);
          const hasDetails = Boolean(source.excerpt || source.source_type || source.chunk_index !== undefined);
          return (
            <article
              className={`source-card source-card-${tone}`}
              key={`${source.file}-${source.chunk_index ?? "file"}-${index}`}
              style={{ animationDelay: `${Math.min(index, 5) * 55}ms` }}
              tabIndex={0}
            >
              <div className="source-card-trigger">
                <span className="source-card-number">{index + 1}</span>
                <span className="source-card-main">
                  <span className="source-card-name" title={source.file}>
                    {sourceTitle(source.file)}
                  </span>
                  <span className="source-card-meta">
                    {source.source_type && (
                      <span><SafetyCertificateOutlined /> {source.source_type}</span>
                    )}
                    {source.chunk_index !== undefined && <span>Chunk {source.chunk_index}</span>}
                    {!hasDetails && <span>Referenced document</span>}
                  </span>
                </span>
              </div>

              <div className="source-card-details">
                <div className="source-card-details-inner">
                  <div className="source-card-file">{source.file}</div>
                  <p>
                    {source.excerpt ||
                      "This cached answer did not store a source excerpt. Open a new answer to retrieve richer citation details."}
                  </p>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export default function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";
  const hasThinking = message.thinking && message.thinking.length > 0;
  const hasContent = message.content && message.content.length > 0;
  const showThinkingPlaceholder = (hasThinking || message.streaming) && !hasContent;

  return (
    <div className={`message-row ${isUser ? "message-user" : "message-assistant"}${message.streaming ? " message-streaming" : ""}`}>
      <div className="message-bubble">
        {(hasThinking || showThinkingPlaceholder) && (
          <div className="process-capsules" style={{ marginBottom: hasContent ? "12px" : "0" }}>
            <span className="process-pill">
              {hasThinking
                ? message.thinking!.map((t, i) => (
                    <span className="process-pill-item" key={i}>
                      {guessThinkingType(t) === "searching" && <SearchOutlined />}
                      {guessThinkingType(t) === "cache" && <DatabaseOutlined />}
                      <span>{processLabel(t)}</span>
                      {i < message.thinking!.length - 1 && <span className="process-divider">/</span>}
                    </span>
                  ))
                : "Analyzing..."}
            </span>
          </div>
        )}

        {isUser ? (
          <Text>{message.content}</Text>
        ) : hasContent ? (
          <div className="markdown-body">
            <ReactMarkdown components={{ code: CodeBlock }}>
              {message.content}
            </ReactMarkdown>
          </div>
        ) : null}

        {message.sources && message.sources.length > 0 && <SourcesPanel sources={message.sources} />}
      </div>
    </div>
  );
}
