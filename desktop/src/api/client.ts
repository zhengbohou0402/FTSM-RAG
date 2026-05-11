import { invoke } from "@tauri-apps/api/core";

let _baseUrl: string | null = null;

async function getBaseUrl(): Promise<string> {
  if (_baseUrl) return _baseUrl;

  // Always ask the Tauri host which backend port it started for this session.
  // This avoids accidentally talking to an unrelated service on port 8000.
  try {
    _baseUrl = await invoke<string>("get_server_url");
  } catch {
    _baseUrl = "http://127.0.0.1:8000";
  }
  return _baseUrl;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const base = await getBaseUrl();
  const res = await fetch(`${base}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
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
}

export interface Document {
  name: string;
  size: number;
  modified: number;
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
  interval_hours: number;
  last_run: string | null;
  next_run: string | null;
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
  const base = await getBaseUrl();
  const res = await fetch(`${base}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || res.statusText);
  }
  const cid = res.headers.get("X-Conversation-Id") || "";
  return { reader: res.body!.getReader(), conversationId: cid };
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
      request<{ ok: boolean }>("/api/settings", { method: "POST", body: JSON.stringify(data) }),
  },
  models: (region?: string) =>
    request<ModelsResponse>(`/api/models${region ? `?list_region=${region}` : ""}`),

  // Documents
  documents: {
    list: () => request<{ documents: Document[] }>("/api/documents"),
    upload: async (files: FileList) => {
      const base = await getBaseUrl();
      const fd = new FormData();
      for (const f of Array.from(files)) fd.append("files", f);
      return fetch(`${base}/api/upload`, { method: "POST", body: fd }).then((r) => r.json()) as Promise<{
        saved: string[];
        errors: string[];
        training_started: boolean;
      }>;
    },
    delete: (filename: string) =>
      request<{ ok: boolean }>(`/api/documents/${encodeURIComponent(filename)}`, { method: "DELETE" }),
  },

  // Training
  training: {
    status: () => request<TrainingStatus>("/api/training/status"),
    start: () => request<{ started: boolean; message: string }>("/api/training/start", { method: "POST" }),
  },

  // Stats
  knowledge: { stats: () => request<KnowledgeStats>("/api/knowledge/stats") },
  cache: { stats: () => request<CacheStats>("/api/cache/stats") },
  scheduler: { status: () => request<SchedulerStatus>("/api/scheduler/status") },
};
