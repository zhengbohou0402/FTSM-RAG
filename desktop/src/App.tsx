import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ConfigProvider, App as AntApp, theme } from "antd";
import { useState, useEffect } from "react";
import Chat from "./pages/Chat";
import Settings from "./pages/Settings";
import Manage from "./pages/Manage";
import Dashboard from "./pages/Dashboard";
import ApiKeySetupModal from "./components/ApiKeySetupModal";
import { api } from "./api/client";

const THEME_KEY = "ftsm_theme";

/**
 * Apple HIG 主题令牌 —— 与网页端 guide.css §11、状态页 legacy.css 同一套。
 *
 * 原配置是 antd 藏青 #2e6da4，而 styles.css 里又是 ChatGPT 绿 #10a37f，
 * 两者和网页端的 teal 体系互不相干 ——「四不像」的三个来源。现在统一：
 *   强调色 = Apple 系统蓝（浅色 #0071e3 / 深色 #0a84ff，同 apple.com）
 *   字体   = SF Pro（-apple-system），不再外链 Inter
 *   中性色 = label / secondaryLabel / separator 三级
 *   圆角   = 10 / 14 / 8 的同心刻度
 */
const appleFont =
  "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', sans-serif";

const sharedTokens = {
  fontFamily: appleFont,
  fontSize: 14,
  borderRadius: 10,
  borderRadiusLG: 14,
  borderRadiusSM: 8,
  controlHeight: 36,
  wireframe: false,
};

const lightTokens = {
  ...sharedTokens,
  colorPrimary: "#0071e3",
  colorInfo: "#0071e3",
  colorLink: "#0066cc",
  colorSuccess: "#248a3d",
  colorWarning: "#b25000",
  colorError: "#d70015",
  colorText: "#1d1d1f",
  colorTextSecondary: "#6e6e73",
  colorTextTertiary: "#86868b",
  colorBorder: "#e5e5ea",
  colorBorderSecondary: "#e5e5ea",
  colorBgContainer: "#ffffff",
  colorBgElevated: "#ffffff",
  colorBgLayout: "#f2f2f7",
  colorFillSecondary: "rgba(120, 120, 128, 0.12)",
  boxShadowSecondary: "0 12px 40px rgba(0, 0, 0, 0.16), 0 2px 8px rgba(0, 0, 0, 0.06)",
};

const darkTokens = {
  ...sharedTokens,
  colorPrimary: "#0a84ff",
  colorInfo: "#0a84ff",
  colorLink: "#409cff",
  colorSuccess: "#30d158",
  colorWarning: "#ff9f0a",
  colorError: "#ff453a",
  colorText: "#f5f5f7",
  colorTextSecondary: "#a1a1a6",
  colorTextTertiary: "#8e8e93",
  colorBorder: "#38383a",
  colorBorderSecondary: "#38383a",
  colorBgContainer: "#1c1c1e",
  colorBgElevated: "#2c2c2e",
  colorBgLayout: "#000000",
  colorFillSecondary: "rgba(120, 120, 128, 0.24)",
  boxShadowSecondary: "0 12px 40px rgba(0, 0, 0, 0.5), 0 2px 8px rgba(0, 0, 0, 0.3)",
};

function AppRoutes({ isDark, onToggleTheme }: { isDark: boolean; onToggleTheme: () => void }) {
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
      <Routes>
        <Route path="/" element={<Chat isDark={isDark} onToggleTheme={onToggleTheme} />} />
        <Route path="/settings" element={<Settings isDark={isDark} onToggleTheme={onToggleTheme} />} />
        <Route path="/manage" element={<Manage isDark={isDark} onToggleTheme={onToggleTheme} />} />
        <Route path="/dashboard" element={<Dashboard isDark={isDark} onToggleTheme={onToggleTheme} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
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
        token: isDark ? darkTokens : lightTokens,
      }}
    >
      <AntApp>
        <BrowserRouter>
          <AppRoutes isDark={isDark} onToggleTheme={() => setIsDark(!isDark)} />
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}

export default App;
