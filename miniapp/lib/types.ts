export type TaskStatus = "open" | "done" | "cancelled";
export type InquiryCategory = "Urgent" | "Sales" | "Team" | "Spam";

export interface Reminder {
  id: string;
  reminder_text: string;
  reminder_time_iso: string;
  event_time_iso: string | null;
  lead_description: string | null;
}

export interface ReminderCreate {
  reminder_text: string;
  reminder_time_iso: string;
  event_time_iso?: string | null;
  lead_description?: string | null;
}

export interface Task {
  id: number;
  description: string;
  assignee_name: string | null;
  assignee_user_id: number | null;
  assignee_username: string | null;
  deadline: string | null;
  status: TaskStatus;
  created_at: string;
  chat_id: number;
}

export interface GhostStatus {
  is_active: boolean;
  away_message: string | null;
  activated_at: string | null;
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
}
