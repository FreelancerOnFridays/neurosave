import type {
  AppSettings,
  GhostStatus,
  Inquiry,
  Reminder,
  ReminderCreate,
  Task,
  TaskStatus,
} from "./types";

// Always use relative URLs in the browser — Next.js rewrites proxy /api/* to the backend.
// The NEXT_PUBLIC_API_URL env var is consumed by next.config.ts rewrites, not here.
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
  reminders: {
    list: () => request<Reminder[]>("/api/reminders"),
    create: (body: ReminderCreate) =>
      request<Reminder>("/api/reminders", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    delete: (id: string) =>
      request<void>(`/api/reminders/${id}`, { method: "DELETE" }),
  },
  tasks: {
    list: () => request<Task[]>("/api/tasks"),
    updateStatus: (id: number, status: TaskStatus) =>
      request<Task>(`/api/tasks/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    nudge: (id: number) =>
      request<void>(`/api/tasks/${id}/nudge`, { method: "POST" }),
  },
  ghost: {
    status: () => request<GhostStatus>("/api/ghost"),
    update: (body: { is_active: boolean; away_message?: string | null }) =>
      request<GhostStatus>("/api/ghost", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
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
