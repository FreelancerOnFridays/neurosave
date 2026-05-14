export type Lang = "ru" | "en";

const ru = {
  nav_today: "Сегодня",
  nav_tasks: "Задачи",
  nav_ghost: "Призрак",
  nav_settings: "Настройки",

  today_reminders_section: "⏰ Мои задачи",
  today_delegated_section: "📌 Делегировано сегодня",

  tasks_subtitle: "Делегированные задачи",

  ghost_active: "Режим призрака включён",
  ghost_inactive: "Режим призрака выключен",
  ghost_since: "Активен с",
  ghost_away_label: "Сообщение об отсутствии",
  ghost_inquiries_section: "📬 Запросы",

  settings_language: "Язык",
  settings_timezone: "Часовой пояс",
  settings_brief_time: "Время брифинга",
  settings_brief_toggle: "Утренний брифинг",
  settings_brief_hint: "HH:MM",

  task_done: "✅ Готово",
  task_nudge: "💬 Напомнить",
  task_cancel: "✕ Отменить",
  task_profile: "👤 Профиль",

  status_open: "Открыто",
  status_done: "Готово",
  status_cancelled: "Отменено",

  cat_urgent: "🔴 Срочно",
  cat_team: "👥 Команда",
  cat_sales: "💼 Продажи",
  cat_spam: "🚫 Спам",

  sec_overdue: "🔴 Просрочено",
  sec_today: "📅 Сегодня",
  sec_upcoming: "⏳ Предстоящие",
  sec_done: "✓ Завершено",

  empty_reminders: "Нет активных напоминаний",
  empty_tasks: "Нет делегированных задач",
  empty_inquiries: "Нет запросов в этой сессии",

  error_loading: "Ошибка загрузки",
  unknown_contact: "Неизвестный",
  profile_link: "👤 Профиль",
} as const;

const en: Record<keyof typeof ru, string> = {
  nav_today: "Today",
  nav_tasks: "Tasks",
  nav_ghost: "Ghost",
  nav_settings: "Settings",

  today_reminders_section: "⏰ My tasks",
  today_delegated_section: "📌 Delegated today",

  tasks_subtitle: "Delegated tasks",

  ghost_active: "Ghost Mode is active",
  ghost_inactive: "Ghost Mode is off",
  ghost_since: "Active since",
  ghost_away_label: "Away message",
  ghost_inquiries_section: "📬 Inquiries",

  settings_language: "Language",
  settings_timezone: "Time zone",
  settings_brief_time: "Brief time",
  settings_brief_toggle: "Morning brief",
  settings_brief_hint: "HH:MM",

  task_done: "✅ Done",
  task_nudge: "💬 Nudge",
  task_cancel: "✕ Cancel",
  task_profile: "👤 Profile",

  status_open: "Open",
  status_done: "Done",
  status_cancelled: "Cancelled",

  cat_urgent: "🔴 Urgent",
  cat_team: "👥 Team",
  cat_sales: "💼 Sales",
  cat_spam: "🚫 Spam",

  sec_overdue: "🔴 Overdue",
  sec_today: "📅 Today",
  sec_upcoming: "⏳ Upcoming",
  sec_done: "✓ Completed",

  empty_reminders: "No active reminders",
  empty_tasks: "No delegated tasks",
  empty_inquiries: "No inquiries this session",

  error_loading: "Failed to load",
  unknown_contact: "Unknown",
  profile_link: "👤 Profile",
};

const strings = { ru, en } as const;

export type TKey = keyof typeof ru;

export function getT(lang: Lang): (key: TKey) => string {
  return (key) => strings[lang][key] ?? strings.en[key];
}
