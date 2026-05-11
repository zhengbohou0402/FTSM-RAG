import { useState, useCallback } from "react";
import { api } from "../api/client";
import type { Message } from "../api/client";

const THINK_RE = /__THINK__([\s\S]*?)__ENDTHINK__/g;

function parseThinking(raw: string): { thinking: string[]; clean: string } {
  const thinking: string[] = [];
  const clean = raw.replace(THINK_RE, (_match, inner) => {
    thinking.push(inner.trim());
    return "";
  });
  return { thinking, clean: clean.trim() };
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const send = useCallback(
    async (text: string) => {
      const userMsg: Message = { role: "user", content: text };
      setMessages((prev) => [...prev, userMsg]);
      setStreaming(true);

      let rawContent = "";
      const assistantMsg: Message = { role: "assistant", content: "", thinking: [] };
      setMessages((prev) => [...prev, assistantMsg]);

      try {
        const { reader, conversationId: cid } = await api.chat(text, conversationId);
        setConversationId(cid);

        const decoder = new TextDecoder();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          rawContent += decoder.decode(value, { stream: true });
          const parsed = parseThinking(rawContent);
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = {
              role: "assistant" as const,
              content: parsed.clean,
              thinking: parsed.thinking.length > 0 ? parsed.thinking : undefined,
            };
            return copy;
          });
        }
      } catch (err) {
        setMessages((prev) => {
          const copy = [...prev];
          copy[copy.length - 1] = {
            role: "assistant",
            content: `Error: ${err instanceof Error ? err.message : "Unknown error"}`,
          };
          return copy;
        });
      } finally {
        setStreaming(false);
      }
    },
    [conversationId]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setConversationId(null);
  }, []);

  const loadConversation = useCallback(async (id: string) => {
    try {
      const conv = await api.conversations.get(id);
      setConversationId(conv.id);
      // Parse thinking blocks from loaded messages too
      const parsed = (conv.messages || []).map((msg) => {
        if (msg.role === "assistant" && !msg.thinking) {
          const result = parseThinking(msg.content);
          return { ...msg, content: result.clean || msg.content, thinking: result.thinking.length > 0 ? result.thinking : undefined };
        }
        return msg;
      });
      setMessages(parsed);
    } catch {
      // conversation may have been deleted
    }
  }, []);

  return { messages, streaming, conversationId, send, clearMessages, loadConversation, setConversationId };
}
