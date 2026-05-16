export type TaskStatus = "open" | "done" | "cancelled";
export type InquiryCategory = "Urgent" | "Sales" | "Team" | "Spam";
export type Theme = "auto" | "light" | "dark";

export interface Task {
  id: number;
  description: string;
  assignee_name: string | null;
  assignee_user_id: number | null;
  assignee_username: string | null;
  deadline: string | null;
  reminder_time: string | null;
  is_personal: boolean;
  status: TaskStatus;
  created_at: string;
  chat_id: number;
  team_label: string | null;
}

export interface GhostStatus {
  is_active: boolean;
  away_message: string | null;
  activated_at: string | null;
  silent_mode: boolean;
}

export interface Inquiry {
  id: number;
  caller_id: number;
  caller_name: string | null;
  caller_username: string | null;
  summary: string | null;
  category: InquiryCategory | null;
  created_at: string;
}

export interface AppSettings {
  language: "ru" | "en";
  timezone: string;
  brief_time: string;
  brief_enabled: boolean;
  theme: Theme;
}

export interface TodaySummary {
  personal_count: number;
  delegated_count: number;
  overdue_count: number;
  with_reminders_count: number;
}

export interface Contact {
  id: number;
  user_id: number;
  name: string | null;
  username: string | null;
  phone: string | null;
  email: string | null;
  team_label: string | null;
  synced_from: "telethon" | "manual" | null;
  last_seen: string | null;
  last_synced_at: string | null;
}

export interface ContactSyncStatus {
  last_sync: string | null;
  telethon_authorized: boolean;
  telethon_configured: boolean;
}

export interface IntegrationStatus {
  provider: string;
  connected: boolean;
  email: string | null;
  scopes: string[];
}

export interface IntegrationsStatus {
  google_calendar: IntegrationStatus;
}
