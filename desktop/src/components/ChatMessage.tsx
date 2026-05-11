import { Card, Collapse, Typography, Tag } from "antd";
import { FileTextOutlined, SearchOutlined, DatabaseOutlined } from "@ant-design/icons";
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

export default function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";

  const hasThinking = message.thinking && message.thinking.length > 0;
  const hasContent = message.content && message.content.length > 0;
  const showThinkingPlaceholder = hasThinking && !hasContent;

  return (
    <div className={`message-row ${isUser ? "message-user" : "message-assistant"}`}>
      <div className="message-bubble">
        {/* Thinking indicator — compact one-liner */}
        {(hasThinking || showThinkingPlaceholder) && (
          <div className="thinking-line">
            <span className="thinking-dot" />
            <span className="thinking-text">
              {hasThinking
                ? message.thinking!.map((t, i) => (
                    <span key={i}>
                      {guessThinkingType(t) === "searching" && <SearchOutlined />}
                      {guessThinkingType(t) === "cache" && <DatabaseOutlined />}
                      {i > 0 ? " · " : ""}{t}
                    </span>
                  ))
                : "Analyzing..."}
            </span>
          </div>
        )}

        {/* Message content */}
        {isUser ? (
          <Text>{message.content}</Text>
        ) : hasContent ? (
          <div className="markdown-body">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        ) : null}

        {message.sources && message.sources.length > 0 && (
          <Collapse
            ghost
            size="small"
            items={[
              {
                key: "sources",
                label: (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <FileTextOutlined /> {message.sources.length} source{message.sources.length > 1 ? "s" : ""}
                  </Text>
                ),
                children: message.sources.map((s, i) => (
                  <Card key={i} size="small" style={{ marginBottom: 8 }}>
                    <Tag color="blue">{s.file}</Tag>
                    <Tag>Chunk {s.chunk_index}</Tag>
                    <Paragraph ellipsis={{ rows: 3 }} style={{ marginTop: 4, fontSize: 12 }}>
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
