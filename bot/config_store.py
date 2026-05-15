from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from beartype import beartype

_TZ_OFFSET_MAP: dict[str, str] = {
    "+0": "UTC",  "+1": "Europe/Berlin",  "+2": "Europe/Kyiv",
    "+3": "Europe/Moscow",  "+4": "Asia/Dubai",  "+5": "Asia/Tashkent",
    "+6": "Asia/Almaty",  "+7": "Asia/Krasnoyarsk",  "+8": "Asia/Shanghai",
    "+9": "Asia/Tokyo",  "+10": "Asia/Vladivostok",  "+11": "Asia/Magadan",
    "+12": "Pacific/Auckland",  "-3": "America/Sao_Paulo",
    "-5": "America/New_York",  "-6": "America/Chicago",
    "-7": "America/Denver",  "-8": "America/Los_Angeles",
}

_CONFIG_FILE = Path(__file__).parent.parent / "bot_config.json"
_SUPPORTED = ("ru", "en")

_STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "task_saved": "📝 Задача принята",
        "tasks_empty": "Нет открытых задач.",
        "task_done_answer": "✅ Задача закрыта",
        "task_deleted_answer": "🗑 Задача удалена",
        "task_not_found": "Задача не найдена",
        "nudge_sent": "👋 Напоминание отправлено",
        "nudge_failed": "Не удалось отправить напоминание",
        "btn_done": "✅ Готово",
        "btn_remind": "👋 Напомнить",
        "btn_delete": "🗑 Удалить",
        "settings_title": "⚙️ <b>Настройки NeuroSave</b>\n\nЯзык: <b>{current_lang}</b>\nЧасовой пояс: <b>{current_tz}</b>\n\nВыберите язык:",
        "lang_ru_label": "🇷🇺 Русский",
        "lang_en_label": "🇬🇧 English",
        "lang_set_ru": "✅ Язык изменён на Русский 🇷🇺",
        "lang_set_en": "✅ Language changed to English 🇬🇧",
        "lang_current_name": "Русский",
    },
    "en": {
        "task_saved": "📝 Task saved",
        "tasks_empty": "No open tasks.",
        "task_done_answer": "✅ Task closed",
        "task_deleted_answer": "🗑 Task deleted",
        "task_not_found": "Task not found",
        "nudge_sent": "👋 Reminder sent",
        "nudge_failed": "Could not send reminder",
        "btn_done": "✅ Done",
        "btn_remind": "👋 Remind",
        "btn_delete": "🗑 Delete",
        "settings_title": "⚙️ <b>NeuroSave Settings</b>\n\nLanguage: <b>{current_lang}</b>\nTimezone: <b>{current_tz}</b>\n\nSelect language:",
        "lang_ru_label": "🇷🇺 Русский",
        "lang_en_label": "🇬🇧 English",
        "lang_set_ru": "✅ Язык изменён на Русский 🇷🇺",
        "lang_set_en": "✅ Language changed to English 🇬🇧",
        "lang_current_name": "English",
    },
}

_config: dict[str, str] = {}


def _load() -> None:
    global _config
    if _CONFIG_FILE.exists():
        _config = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    else:
        _config = {"language": "ru"}


def _persist() -> None:
    _CONFIG_FILE.write_text(
        json.dumps(_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@beartype
def get_language() -> str:
    return _config.get("language", "ru")


@beartype
def set_language(lang: str) -> None:
    if lang not in _SUPPORTED:
        raise ValueError(f"Unsupported language: {lang}")
    _config["language"] = lang
    _persist()


@beartype
def t(key: str) -> str:
    lang = get_language()
    strings = _STRINGS.get(lang, _STRINGS["ru"])
    return strings.get(key, key)


@beartype
def get_timezone() -> str:
    return _config.get("timezone", "Europe/Moscow")


@beartype
def set_timezone(tz_name: str) -> None:
    resolved = _TZ_OFFSET_MAP.get(tz_name, tz_name)
    try:
        ZoneInfo(resolved)
    except (KeyError, ZoneInfoNotFoundError):
        raise ValueError(f"Unknown timezone: {tz_name}")
    _config["timezone"] = resolved
    _persist()


def get_business_connection_id() -> str | None:
    val = _config.get("business_connection_id", "")
    return val if val else None


@beartype
def set_business_connection_id(bcid: str) -> None:
    _config["business_connection_id"] = bcid
    _persist()


@beartype
def get_brief_time() -> str:
    return _config.get("brief_time", "09:00")


@beartype
def set_brief_time(time_str: str) -> None:
    parts = time_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {time_str}")
    h, m = parts
    if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
        raise ValueError(f"Invalid time: {time_str}")
    _config["brief_time"] = f"{int(h):02d}:{int(m):02d}"
    _persist()


@beartype
def get_last_brief_date() -> str:
    return _config.get("last_brief_date", "")


@beartype
def set_last_brief_date(date_str: str) -> None:
    _config["last_brief_date"] = date_str
    _persist()


@beartype
def is_brief_enabled() -> bool:
    return _config.get("brief_enabled", "true") != "false"


@beartype
def set_brief_enabled(enabled: bool) -> None:
    _config["brief_enabled"] = "true" if enabled else "false"
    _persist()


_SUPPORTED_THEMES = ("auto", "light", "dark")


@beartype
def get_theme() -> str:
    return _config.get("theme", "auto")


@beartype
def set_theme(theme: str) -> None:
    if theme not in _SUPPORTED_THEMES:
        raise ValueError(f"Unsupported theme: {theme}")
    _config["theme"] = theme
    _persist()


_load()
