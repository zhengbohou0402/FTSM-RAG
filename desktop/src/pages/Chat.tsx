import { useEffect, useRef } from "react";
import { Layout } from "antd";
import Sidebar from "../components/Sidebar";
import ChatMessage from "../components/ChatMessage";
import Composer from "../components/Composer";
import { useChat } from "../hooks/useChat";
import { useConversations } from "../hooks/useConversations";

const { Sider, Content, Header } = Layout;

export default function Chat() {
  const {
    messages,
    streaming,
    conversationId,
    send,
    loadConversation,
    clearMessages,
    setConversationId,
  } = useChat();
  const { conversations, loading: convLoading, refresh, create, remove, removeAll } = useConversations();
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    const handleNew = () => {
      void handleNewChat();
    };
    const handleClearAll = () => {
      removeAll();
      clearMessages();
    };
    window.addEventListener("new-chat", handleNew);
    window.addEventListener("clear-chat", handleClearAll);
    return () => {
      window.removeEventListener("new-chat", handleNew);
      window.removeEventListener("clear-chat", handleClearAll);
    };
  }, [clearMessages, removeAll]);

  const handleNewChat = async () => {
    const conv = await create();
    clearMessages();
    setConversationId(conv.id);
  };

  const handleSelectConv = (id: string) => {
    loadConversation(id);
  };

  const handleDeleteConv = (id: string) => {
    if (id === conversationId) clearMessages();
    remove(id);
  };

  return (
    <Layout style={{ height: "100%" }}>
      <Sider
        width={280}
        breakpoint="lg"
        collapsedWidth={0}
        trigger={null}
        className="chat-sidebar"
      >
        <div className="sidebar-wrapper">
          <Sidebar
            conversations={conversations}
            activeId={conversationId}
            loading={convLoading}
            onSelect={handleSelectConv}
            onNew={handleNewChat}
            onDelete={handleDeleteConv}
          />

        </div>
      </Sider>
      <Layout className="chat-main">
        <Header className="chat-header">
          <span className="chat-header-title">FTSM-RAG Assistant</span>
        </Header>
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
    </Layout>
  );
}
