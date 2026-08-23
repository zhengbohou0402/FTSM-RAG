import { useState, useCallback } from "react";
import { api } from "../api/client";
import type { Message } from "../api/client";
import { parseAssistantMessage } from "../utils/messageParser";

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
      const assistantMsg: Message = { role: "assistant", content: "", thinking: [], streaming: true };
      setMessages((prev) => [...prev, assistantMsg]);

      try {
        const { reader, conversationId: cid } = await api.chat(text, conversationId);
        setConversationId(cid);

        const decoder = new TextDecoder();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          rawContent += decoder.decode(value, { stream: true });
          const parsed = parseAssistantMessage(rawContent, true);
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = parsed;
            return copy;
          });
        }
        setMessages((prev) => {
          const copy = [...prev];
          copy[copy.length - 1] = parseAssistantMessage(rawContent);
          return copy;
        });
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
          return parseAssistantMessage(msg.content);
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
