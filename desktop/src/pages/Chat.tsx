import { useEffect, useRef } from "react";
import { Layout } from "antd";
import ChatMessage from "../components/ChatMessage";
import Composer from "../components/Composer";
import { useChat } from "../hooks/useChat";

const { Content } = Layout;

export default function Chat() {
  const {
    messages,
    streaming,
    send,
    loadConversation,
    clearMessages,
    setConversationId,
  } = useChat();
  const chatRef = useRef<HTMLDivElement>(null);


  useEffect(() => {
    const timer = setTimeout(() => {
      if (chatRef.current) {
        chatRef.current.scrollTop = chatRef.current.scrollHeight;
      }
    }, 10);
    return () => clearTimeout(timer);
  }, [messages]);

  useEffect(() => {
    const handleNew = () => {
      void handleNewChat();
    };
    const handleClearAll = () => {
      clearMessages();
      setConversationId(null);
    };
    const handleLoad = (e: CustomEvent) => {
      loadConversation(e.detail);
    };

    window.addEventListener("new-chat", handleNew);
    window.addEventListener("clear-chat", handleClearAll);
    window.addEventListener("load-chat", handleLoad as EventListener);
    
    return () => {
      window.removeEventListener("new-chat", handleNew);
      window.removeEventListener("clear-chat", handleClearAll);
      window.removeEventListener("load-chat", handleLoad as EventListener);
    };
  }, [clearMessages, loadConversation]);

  const handleNewChat = async () => {
    // Relying on GlobalSidebar to create and send 'load-chat' now, 
    // but keep local fallback if triggered directly
    clearMessages();
    setConversationId(null);
  };

  return (
    <Layout className="chat-main" style={{ flex: 1, minHeight: 0, borderRadius: 0 }}>

      <Content className="chat-content" ref={chatRef as React.RefObject<HTMLDivElement>}>
        {messages.length === 0 ? (
          <div className="welcome">
            <h1>How can I help you today?</h1>
            <p>Ask about UKM FTSM academic calendars, registration, visas, and student life.</p>
          </div>
        ) : (
          messages.map((msg, i) => <ChatMessage key={i} message={msg} />)
        )}
      </Content>
      <div className="chat-footer">
        <Composer onSend={send} disabled={streaming} />
      </div>
    </Layout>
  );
}
