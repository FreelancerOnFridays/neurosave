import type {
  AppSettings,
  GhostStatus,
  Inquiry,
  Task,
  TaskStatus,
} from "./types";

const BASE_URL = "";

let _initData = "";

export function setInitData(initData: string): void {
  _initData = initData;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `tma ${_initData}`,
      ...(options.headers as Record<string, string>),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  tasks: {
    list: (params?: { type?: string; has_reminder?: boolean; date?: string }) => {
      const q = new URLSearchParams();
      if (params?.type) q.set("type", params.type);
      if (params?.has_reminder !== undefined) q.set("has_reminder", String(params.has_reminder));
      if (params?.date) q.set("date", params.date);
      const qs = q.toString();
      return request<Task[]>(`/api/tasks${qs ? `?${qs}` : ""}`);
    },
    create: (body: { description: string; deadline?: string | null; reminder_time?: string | null }) =>
      request<Task>("/api/tasks", { method: "POST", body: JSON.stringify(body) }),
    updateStatus: (id: number, status: TaskStatus) =>
      request<Task>(`/api/tasks/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    setReminder: (id: number, reminder_time: string | null) =>
      request<Task>(`/api/tasks/${id}/reminder`, {
        method: "PATCH",
        body: JSON.stringify({ reminder_time }),
      }),
    deleteReminder: (id: number) =>
      request<Task>(`/api/tasks/${id}/reminder`, { method: "DELETE" }),
    delete: (id: number) =>
      request<void>(`/api/tasks/${id}`, { method: "DELETE" }),
    nudge: (id: number) =>
      request<void>(`/api/tasks/${id}/nudge`, { method: "POST" }),
  },
  ghost: {
    status: () => request<GhostStatus>("/api/ghost"),
    update: (body: { is_active: boolean; away_message?: string | null; silent_mode?: boolean }) =>
      request<GhostStatus>("/api/ghost", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    setSilent: (silent_mode: boolean) =>
      request<GhostStatus>("/api/ghost/silent", {
        method: "PATCH",
        body: JSON.stringify({ silent_mode }),
      }),
    generateReply: () =>
      request<{ text: string }>("/api/ghost/generate-reply", { method: "POST" }),
    inquiries: () => request<Inquiry[]>("/api/ghost/inquiries"),
  },
  settings: {
    get: () => request<AppSettings>("/api/settings"),
    update: (body: Partial<AppSettings>) =>
      request<AppSettings>("/api/settings", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
  },
};
