import { Card, Collapse, Typography, Tag } from "antd";
import { DatabaseOutlined, FileTextOutlined, SearchOutlined } from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import type { Message } from "../api/client";

const { Text, Paragraph } = Typography;

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

export default function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";
  const hasThinking = message.thinking && message.thinking.length > 0;
  const hasContent = message.content && message.content.length > 0;
  const showThinkingPlaceholder = hasThinking && !hasContent;

  return (
    <div className={`message-row ${isUser ? "message-user" : "message-assistant"}`}>
      <div className="message-bubble">
        {(hasThinking || showThinkingPlaceholder) && (
          <div className="process-capsules">
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
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        ) : null}

        {message.sources && message.sources.length > 0 && (
          <Collapse
            className="sources-collapse"
            ghost
            size="small"
            items={[
              {
                key: "sources",
                label: (
                  <Text type="secondary" className="sources-label">
                    <FileTextOutlined /> {message.sources.length} source{message.sources.length > 1 ? "s" : ""}
                  </Text>
                ),
                children: message.sources.map((s, i) => (
                  <Card className="source-card-react" key={i} size="small">
                    <Tag color="blue">{s.file}</Tag>
                    {s.source_type && <Tag color="green">{s.source_type}</Tag>}
                    <Tag>Chunk {s.chunk_index}</Tag>
                    <Paragraph ellipsis={{ rows: 3 }} className="source-excerpt-react">
                      {s.excerpt}
                    </Paragraph>
                  </Card>
                )),
              },
            ]}
          />
        )}
      </div>
    </div>
  );
}
