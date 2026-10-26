import { invoke } from "@tauri-apps/api/core";

let _baseUrl: string | null = null;

async function getBaseUrl(): Promise<string> {
  if (_baseUrl) return _baseUrl;

  try {
    // Desktop mode: ask the Tauri host which backend port it started.
    _baseUrl = await invoke<string>("get_server_url");
  } catch {
    const location = window.location;
    const isViteDevServer = ["5173", "5174"].includes(location.port);
    _baseUrl = isViteDevServer ? "http://127.0.0.1:8000" : location.origin;
  }
  return _baseUrl;
}

function guestCredentials(): { studentId: string; displayName: string; password: string } {
  try {
    const raw = typeof localStorage !== "undefined" ? localStorage.getItem("ftsm_guest") : null;
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.studentId && parsed.password) return parsed;
    }
  } catch {}
  const rand = Math.random().toString(36).slice(2, 10);
  const creds = {
    studentId: "student_" + rand,
    displayName: "Student " + rand.slice(0, 4).toUpperCase(),
    password: Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2),
  };
  try {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem("ftsm_guest", JSON.stringify(creds));
    }
  } catch {}
  return creds;
}

let _ensuringSession: Promise<boolean> | null = null;

export async function ensureSession(force = false): Promise<boolean> {
  if (_ensuringSession && !force) return _ensuringSession;
  _ensuringSession = (async () => {
    const base = await getBaseUrl();
    if (!force) {
      try {
        const res = await fetch(`${base}/api/auth/me`, { credentials: "include" });
        if (res.ok) {
          const data = await res.json().catch(() => ({}));
          if (data && (data as { authenticated?: boolean }).authenticated) return true;
        }
      } catch {
        // Fall through
      }
    }
    for (let attempt = 0; attempt < 2; attempt++) {
      const creds = guestCredentials();
      try {
        const reg = await fetch(`${base}/api/auth/register`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(creds),
        });
        if (reg.ok) return true;
        if (reg.status === 409) {
          const login = await fetch(`${base}/api/auth/login`, {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(creds),
          });
          if (login.ok) return true;
        }
      } catch {
        return false;
      }
      try {
        if (typeof localStorage !== "undefined") {
          localStorage.removeItem("ftsm_guest");
        }
      } catch {}
    }
    return false;
  })().finally(() => {
    _ensuringSession = null;
  });
  return _ensuringSession;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const base = await getBaseUrl();
  let res = await fetch(`${base}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    const recovered = await ensureSession(true);
    if (recovered) {
      res = await fetch(`${base}${path}`, {
        credentials: "include",
        headers: { "Content-Type": "application/json", ...options?.headers },
        ...options,
      });
    }
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || res.statusText);
  }
  return res.json();
}

export interface Conversation {
  id: string;
  title: string;
  updated_at: number;
  messages?: Message[];
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  thinking?: string[];
}

export interface Source {
  file: string;
  chunk_index: number;
  excerpt: string;
  source_type?: string;
}

export interface Document {
  name: string;
  source?: "official" | "upload";
  size: number;
  modified: number;
  indexed?: boolean;
  stale?: boolean;
  chunks?: number;
  source_type?: string | null;
  source_trust_label?: string | null;
  indexed_at?: string | null;
  covered_by?: string | null;
  index_note?: string | null;
}

export interface TrainingStatus {
  running: boolean;
  pending: boolean;
  last_result: string | null;
  last_error: string | null;
}

export interface KnowledgeStats {
  document_count: number;
  manifest_records: number;
  total_chunks: number;
  last_indexed: string | null;
  cache_entries: number;
  index_version: number;
  index_updated_at: string | null;
  index_last_error: string | null;
  source_type_counts: Record<string, number>;
}

export interface CacheStats {
  hit_count: number;
  miss_count: number;
  hit_rate: number;
  size: number;
  valid: number;
  threshold: number;
}

export interface SchedulerStatus {
  enabled: boolean;
  manual_available: boolean;
  interval_hours: number;
  max_pages: number;
  last_run: string | null;
  next_run: string | null;
  running: boolean;
  mode: "scheduled" | "manual" | null;
  phase: "idle" | "crawling" | "indexing";
  last_success: string | null;
  last_attempt: string | null;
  last_error: string | null;
  last_output_file: string | null;
  pages_crawled: number;
  thread_alive: boolean;
}

export interface Settings {
  dashscope_api_key: string;
  dashscope_base_url: string;
  chat_model_name: string;
}

export interface ModelsResponse {
  models: string[];
  key_valid: boolean | null;
  key_error: string;
  region: string;
}

export async function streamChat(
  message: string,
  conversationId: string | null
): Promise<{ reader: ReadableStreamDefaultReader<Uint8Array>; conversationId: string }> {
  await ensureSession();
  const base = await getBaseUrl();
  let res = await fetch(`${base}/api/chat`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
  if (res.status === 401) {
    const recovered = await ensureSession(true);
    if (recovered) {
      res = await fetch(`${base}/api/chat`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, conversation_id: conversationId }),
      });
    }
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || res.statusText);
  }
  const cid = res.headers.get("X-Conversation-Id") || "";
  return { reader: res.body!.getReader(), conversationId: cid };
}

// P0-3：全局配置写操作需要管理员密钥（本地开发把 key 存在 localStorage）
function adminHeaders(): Record<string, string> {
  const key = typeof localStorage !== "undefined" ? localStorage.getItem("ftsm_admin_key") || "" : "";
  return key ? { "X-Admin-Api-Key": key } : {};
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  configStatus: () => request<{ dashscope_configured: boolean }>("/api/config/status"),
  chat: streamChat,

  // Conversations
  conversations: {
    list: () => request<{ items: Conversation[] }>("/api/conversations"),
    create: () => request<Conversation>("/api/conversations", { method: "POST" }),
    get: (id: string) => request<Conversation>(`/api/conversations/${id}`),
    delete: (id: string) => request<{ ok: boolean }>(`/api/conversations/${id}`, { method: "DELETE" }),
  },

  // Settings
  settings: {
    get: () => request<Settings>("/api/settings"),
    save: (data: { dashscope_api_key: string; dashscope_base_url: string; chat_model_name: string }) =>
      request<{ ok: boolean }>("/api/settings", { method: "POST", headers: adminHeaders(), body: JSON.stringify(data) }),
  },
  models: (region?: string) =>
    request<ModelsResponse>(`/api/models${region ? `?list_region=${region}` : ""}`),

  // Documents
  documents: {
    list: () => request<{ documents: Document[] }>("/api/documents"),
    upload: async (files: FileList) => {
      await ensureSession();
      const base = await getBaseUrl();
      const fd = new FormData();
      for (const f of Array.from(files)) fd.append("files", f);
      let res = await fetch(`${base}/api/upload`, {
        method: "POST",
        credentials: "include",
        body: fd,
      });
      if (res.status === 401) {
        const recovered = await ensureSession(true);
        if (recovered) {
          res = await fetch(`${base}/api/upload`, {
            method: "POST",
            credentials: "include",
            body: fd,
          });
        }
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail || res.statusText);
      }
      return (await res.json()) as {
        saved: string[];
        errors: { name: string; error: string }[];
        training_started: boolean;
      };
    },
    delete: (filename: string) =>
      // FastAPI {filename:path} 按 `/` 分段匹配 —— 整段 encode 会把 `uploads/`
      // 的斜杠变成 %2F 而路由 404；必须按段分别编码
      request<{ ok: boolean }>(
        `/api/documents/${filename.split("/").map(encodeURIComponent).join("/")}`,
        { method: "DELETE" }
      ),
  },

  // Training
  training: {
    status: () => request<TrainingStatus>("/api/training/status"),
    start: () => request<{ started: boolean; message: string }>("/api/training/start", { method: "POST" }),
  },

  // Stats
  knowledge: {
    stats: () => request<KnowledgeStats>("/api/knowledge/stats"),
    update: (reindex = true) => request<{ started: boolean; message: string; max_pages: number; reindex: boolean }>(
      `/api/knowledge/update?reindex=${reindex ? "true" : "false"}`,
      { method: "POST", headers: adminHeaders() }
    ),
  },
  cache: { stats: () => request<CacheStats>("/api/cache/stats") },
  scheduler: { status: () => request<SchedulerStatus>("/api/scheduler/status") },
};
