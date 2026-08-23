import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ConfigProvider, App as AntApp, theme } from "antd";
import { useState, useEffect } from "react";
import Chat from "./pages/Chat";
import Settings from "./pages/Settings";
import Manage from "./pages/Manage";
import Dashboard from "./pages/Dashboard";
import Prompts from "./pages/Prompts";
// ── TRILINGUAL DEMO FEATURE ──
import TrilingualCompare from "./pages/TrilingualCompare";
// ── END TRILINGUAL DEMO FEATURE ──
import ApiKeySetupModal from "./components/ApiKeySetupModal";
import GlobalSidebar from "./components/GlobalSidebar";
import { api } from "./api/client";

const THEME_KEY = "ftsm_theme";

function AppRoutes({ onToggleTheme }: { onToggleTheme: () => void }) {
  const location = useLocation();
  const [dashscopeConfigured, setDashscopeConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      while (!cancelled) {
        try {
          await api.health();
        } catch {
          await new Promise((r) => setTimeout(r, 1000));
          continue;
        }
        try {
          const s = await api.configStatus();
          if (!cancelled) {
            // 仅当接口明确返回 true 视为已配置（避免字段缺失时误判）
            setDashscopeConfigured(s.dashscope_configured === true);
          }
        } catch {
          // 后端已通但读配置失败时仍弹出引导，避免状态卡在 null 永远不弹窗
          if (!cancelled) setDashscopeConfigured(false);
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
    }
    poll();
    return () => {
      cancelled = true;
    };
  }, []);

  const showApiKeyModal =
    dashscopeConfigured === false && location.pathname !== "/settings";

  return (
    <>
      <ApiKeySetupModal
        open={showApiKeyModal}
        onSuccess={() => setDashscopeConfigured(true)}
      />
      <div style={{ display: "flex", flexDirection: "row", height: "100vh", overflow: "hidden" }}>
        <GlobalSidebar onToggleTheme={onToggleTheme} />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: location.pathname === "/" ? "hidden" : "auto" }}>
          <Routes>
            <Route path="/" element={<Chat />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/manage" element={<Manage />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/prompts" element={<Prompts />} />
            {/* ── TRILINGUAL DEMO FEATURE ── */}
            <Route path="/compare" element={<TrilingualCompare />} />
            {/* ── END TRILINGUAL DEMO FEATURE ── */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </div>
    </>
  );
}

function App() {
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem(THEME_KEY);
    return saved === "dark";
  });

  useEffect(() => {
    localStorage.setItem(THEME_KEY, isDark ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");
  }, [isDark]);

  return (
    <ConfigProvider
      theme={{
        algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          colorPrimary: "#2e6da4",
          borderRadius: 8,
          colorBgContainer: isDark ? "#1a1a2e" : "#ffffff",
        },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <AppRoutes onToggleTheme={() => setIsDark(!isDark)} />
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}

export default App;
