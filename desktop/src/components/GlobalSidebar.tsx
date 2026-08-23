import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Button, List, Typography, Tooltip, message, Popconfirm } from "antd";
import {
  PlusOutlined,
  MessageOutlined,
  DeleteOutlined,
  FileSearchOutlined,
  DashboardOutlined,
  SettingOutlined,
  BulbOutlined,
  PlayCircleOutlined,
  ClearOutlined,
  MenuUnfoldOutlined,
  MenuFoldOutlined,
  GlobalOutlined,
} from "@ant-design/icons";
import { useConversations } from "../hooks/useConversations";
import { api } from "../api/client";

const { Text } = Typography;

interface Props {
  onToggleTheme: () => void;
}

export default function GlobalSidebar({ onToggleTheme }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem("ftsm_sidebar_collapsed") === "true";
  });
  
  const { conversations, loading, refresh, create, remove, removeAll } = useConversations();

  // Active conversation ID from window location state or event
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    refresh();
    
    // Listen for clear all events from other parts if any
    const handleRefresh = () => refresh();
    window.addEventListener("refresh-conversations", handleRefresh);
    return () => window.removeEventListener("refresh-conversations", handleRefresh);
  }, [refresh]);

  useEffect(() => {
    localStorage.setItem("ftsm_sidebar_collapsed", String(collapsed));
  }, [collapsed]);

  // Keep activeId in sync with navigation state
  useEffect(() => {
    if (location.pathname === "/" && location.state?.loadId) {
      setActiveId(location.state.loadId);
    } else if (location.pathname !== "/") {
      setActiveId(null);
    }
  }, [location.pathname, location.state]);

  const handleNewChat = async () => {
    try {
      const conv = await create();
      setActiveId(conv.id);
      if (location.pathname !== "/") {
        navigate("/", { state: { loadId: conv.id } });
      } else {
        window.dispatchEvent(new CustomEvent("load-chat", { detail: conv.id }));
      }
    } catch (err) {
      message.error("Failed to create new chat");
    }
  };

  const handleSelectConv = (id: string) => {
    setActiveId(id);
    if (location.pathname !== "/") {
      navigate("/", { state: { loadId: id } });
    } else {
      window.dispatchEvent(new CustomEvent("load-chat", { detail: id }));
    }
  };

  const handleDeleteConv = async (id: string) => {
    await remove(id);
    if (activeId === id) {
      window.dispatchEvent(new CustomEvent("clear-chat"));
      setActiveId(null);
    }
  };

  const handleClearAll = async () => {
    await removeAll();
    window.dispatchEvent(new CustomEvent("clear-chat"));
    setActiveId(null);
  };

  const handleTriggerIndexing = async () => {
    try {
      const res = await api.training.start();
      if (res.started) {
        message.success("Knowledge base indexing started in the background.");
      } else {
        message.info(res.message || "Indexing is already running.");
      }
    } catch (err) {
      message.error(`Failed to start indexing: ${err}`);
    }
  };

  const navItems = [
    { key: "/", icon: <MessageOutlined />, label: "Chat" },
    { key: "/compare", icon: <GlobalOutlined />, label: "Compare Models" },
    { key: "/manage", icon: <FileSearchOutlined />, label: "Knowledge" },
    { key: "/dashboard", icon: <DashboardOutlined />, label: "Dashboard" },
    { key: "/prompts", icon: <MessageOutlined />, label: "Prompts" },
    { key: "/settings", icon: <SettingOutlined />, label: "Settings" },
  ];

  return (
    <div className={`global-sidebar ${collapsed ? "collapsed" : ""}`}>
      {/* Header */}
      <div className="global-sidebar-header">
        {!collapsed && (
          <div className="global-sidebar-logo" onClick={() => navigate("/")}>
            <span className="logo-text">FTSM-RAG</span>
          </div>
        )}
        <Button 
          type="text" 
          icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} 
          onClick={() => setCollapsed(!collapsed)}
          className="collapse-btn"
        />
      </div>

      {/* Main Actions */}
      <div className="global-sidebar-actions">
        <Button 
          type="primary" 
          block={!collapsed} 
          icon={<PlusOutlined />} 
          onClick={handleNewChat}
          className={collapsed ? "collapsed-btn" : ""}
          title={collapsed ? "New Chat" : undefined}
        >
          {!collapsed && "New Chat"}
        </Button>
      </div>

      {/* Main Navigation (Moved here) */}
      <div className="global-sidebar-nav">
        {navItems.map((item) => (
          <Tooltip title={collapsed ? item.label : ""} placement="right" key={item.key}>
            <div 
              className={`footer-nav-item ${location.pathname === item.key ? "active" : ""}`}
              onClick={() => navigate(item.key)}
            >
              <span className="item-icon">{item.icon}</span>
              {!collapsed && <span className="item-text">{item.label}</span>}
            </div>
          </Tooltip>
        ))}
      </div>

      {/* Conversations List */}
      <div className="global-sidebar-list-container">
        {!collapsed && (
          <div className="list-header" style={{ marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: "12px", fontWeight: 600 }}>Recent</Text>
            {conversations.length > 0 && (
              <Popconfirm
                title="Clear all chats?"
                onConfirm={handleClearAll}
                okText="Yes"
                cancelText="No"
              >
                <Button type="text" size="small" icon={<ClearOutlined />} title="Clear All" />
              </Popconfirm>
            )}
          </div>
        )}
        <div className="global-sidebar-list">
          <List
            loading={loading && conversations.length === 0}
            dataSource={conversations}
            renderItem={(item) => (
              <Tooltip title={collapsed ? item.title || "New chat" : ""} placement="right">
                <div
                  className={`global-sidebar-item ${item.id === activeId ? "active" : ""}`}
                  onClick={() => handleSelectConv(item.id)}
                >
                  <MessageOutlined className="item-icon" />
                  {!collapsed && (
                    <>
                      <Text ellipsis className="item-text">
                        {item.title || "New chat"}
                      </Text>
                      <Button
                        type="text"
                        size="small"
                        danger
                        className="delete-btn"
                        icon={<DeleteOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteConv(item.id);
                        }}
                      />
                    </>
                  )}
                </div>
              </Tooltip>
            )}
          />
        </div>
      </div>

      {/* Bottom Navigation (Settings & Tools only) */}
      <div className="global-sidebar-footer">
        
        <Tooltip title={collapsed ? "Index Knowledge" : ""} placement="right">
          <div className="footer-nav-item" onClick={handleTriggerIndexing}>
            <span className="item-icon"><PlayCircleOutlined /></span>
            {!collapsed && <span className="item-text">Index Knowledge</span>}
          </div>
        </Tooltip>

        <Tooltip title={collapsed ? "Toggle Theme" : ""} placement="right">
          <div className="footer-nav-item" onClick={onToggleTheme}>
            <span className="item-icon"><BulbOutlined /></span>
            {!collapsed && <span className="item-text">Toggle Theme</span>}
          </div>
        </Tooltip>
      </div>
    </div>
  );
}
