import { useEffect, useRef } from "react";
import { Button, Layout } from "antd";
import {
  AppstoreOutlined,
  BulbFilled,
  BulbOutlined,
  DashboardOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Link } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import ChatMessage from "../components/ChatMessage";
import Composer from "../components/Composer";
import { useChat } from "../hooks/useChat";
import { useConversations } from "../hooks/useConversations";

const { Sider, Content, Header } = Layout;

interface Props {
  isDark: boolean;
  onToggleTheme: () => void;
}

export default function Chat({ isDark, onToggleTheme }: Props) {
  const {
    messages,
    streaming,
    conversationId,
    send,
    loadConversation,
    clearMessages,
    setConversationId,
  } = useChat();
  const { conversations, loading: convLoading, refresh, create, remove } = useConversations();
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

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
    <Layout style={{ height: "100vh" }}>
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
          <div className="sidebar-foot">
            <Button type="text" icon={isDark ? <BulbFilled /> : <BulbOutlined />} onClick={onToggleTheme} />
            <Link to="/settings">
              <Button type="text" icon={<SettingOutlined />} />
            </Link>
            <Link to="/manage">
              <Button type="text" icon={<AppstoreOutlined />} />
            </Link>
            <Link to="/dashboard">
              <Button type="text" icon={<DashboardOutlined />} />
            </Link>
          </div>
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
