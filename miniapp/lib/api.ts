import type {
  AppSettings,
  CalendarEvent,
  Contact,
  ContactSyncStatus,
  GhostStatus,
  GmailMessage,
  GmailThread,
  Inquiry,
  IntegrationsStatus,
  Task,
  TaskStatus,
} from "./types";

const BASE_URL = "";

let _initData = "";
let _authReadyResolve: (() => void) | null = null;

const _authReady = new Promise<void>((resolve) => {
  if (typeof window !== "undefined" && window.Telegram?.WebApp?.initData) {
    _initData = window.Telegram.WebApp.initData;
    resolve();
  } else {
    _authReadyResolve = resolve;
    setTimeout(resolve, 2000);
  }
});

export function setInitData(initData: string): void {
  _initData = initData;
  _authReadyResolve?.();
  _authReadyResolve = null;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  await _authReady;
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
    nudgePreview: (id: number) =>
      request<{ text: string }>(`/api/tasks/${id}/nudge/preview`),
    nudge: (id: number, text?: string) =>
      request<void>(`/api/tasks/${id}/nudge`, {
        method: "POST",
        body: text ? JSON.stringify({ text }) : undefined,
      }),
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
    setExclusions: (contact_ids: number[], labels: string[]) =>
      request<GhostStatus>("/api/ghost/exclusions", {
        method: "PATCH",
        body: JSON.stringify({ contact_ids, labels }),
      }),
    setAutoOff: (auto_off_at: string | null) =>
      request<GhostStatus>("/api/ghost/auto-off", {
        method: "PATCH",
        body: JSON.stringify({ auto_off_at }),
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
  contacts: {
    list: () => request<Contact[]>("/api/contacts"),
    status: () => request<ContactSyncStatus>("/api/contacts/status"),
    update: (user_id: number, body: { saved_name?: string | null; email?: string | null }) =>
      request<Contact>(`/api/contacts/${user_id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    avatarUrl: (user_id: number) => `/api/contacts/${user_id}/avatar`,
    getLabels: () => request<string[]>("/api/contacts/labels"),
    setLabels: (user_id: number, labels: string[]) =>
      request<Contact>(`/api/contacts/${user_id}/labels`, {
        method: "PUT",
        body: JSON.stringify({ labels }),
      }),
  },
  integrations: {
    status: () => request<IntegrationsStatus>("/api/integrations/status"),
    googleAuthUrl: () => request<{ url: string }>("/api/integrations/google/auth-url"),
    googleDisconnect: () => request<void>("/api/integrations/google", { method: "DELETE" }),
    gmailAuthUrl: () => request<{ url: string }>("/api/integrations/gmail/auth-url"),
    gmailDisconnect: () => request<void>("/api/integrations/gmail", { method: "DELETE" }),
    gmailThreads: (limit = 20) =>
      request<GmailThread[]>(`/api/integrations/gmail/threads?limit=${limit}`),
    gmailMessage: (id: string) =>
      request<GmailMessage>(`/api/integrations/gmail/messages/${id}`),
    gmailSend: (body: { to: string; subject: string; body: string; thread_id?: string | null; in_reply_to?: string | null }) =>
      request<{ id: string }>("/api/integrations/gmail/send", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    redirectUris: () => request<{ base_url: string; redirect_uris: string[] }>("/api/integrations/redirect-uris"),
    gmailNotifications: () => request<{ enabled: boolean }>("/api/integrations/gmail/notifications"),
    setGmailNotifications: (enabled: boolean) =>
      request<{ enabled: boolean }>("/api/integrations/gmail/notifications", {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      }),
    calendarEvents: (days = 7) =>
      request<CalendarEvent[]>(`/api/integrations/google-calendar/events?days=${days}`),
    calendarToday: () =>
      request<CalendarEvent[]>("/api/integrations/calendar/today"),
  },
  bot: {
    sendTutorial: () => request<{ ok: boolean }>("/api/bot/tutorial", { method: "POST" }),
  },
};
