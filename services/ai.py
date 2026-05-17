from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from beartype import beartype
from openai import AsyncOpenAI
from pydantic import BaseModel

from config import settings
from db.models import InquiryCategory, Message

logger = logging.getLogger(__name__)

GPT_MODEL = "gpt-5.4-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

_client: AsyncOpenAI | None = None

_LANG_NAMES = {"ru": "Russian", "en": "English"}

_style_cache: dict[int, tuple[str, datetime]] = {}
_STYLE_TTL = timedelta(hours=1)


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


@beartype
async def extract_style_profile(texts: list[str]) -> str:
    sample = "\n---\n".join(texts[:30])
    client = _get_client()
    completion = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Analyze the following message samples written by one person and describe their "
                    "writing style in 2-3 sentences. Focus on: sentence length, formality level, "
                    "punctuation habits, emoji usage, tone, and any recurring patterns. "
                    "Be specific — this description will instruct an AI to write in the same style."
                ),
            },
            {"role": "user", "content": sample},
        ],
        max_completion_tokens=150,
    )
    return (completion.choices[0].message.content or "").strip()


@beartype
async def get_style_profile(owner_id: int, texts: list[str]) -> str:
    """Returns a cached style descriptor, refreshing if older than 1 hour."""
    now = datetime.now(timezone.utc)
    cached = _style_cache.get(owner_id)
    if cached and (now - cached[1]) < _STYLE_TTL:
        return cached[0]
    if not texts:
        return ""
    profile = await extract_style_profile(texts)
    _style_cache[owner_id] = (profile, now)
    return profile


class ExtractedTask(BaseModel):
    has_task: bool
    description: str | None = None
    assignee_name: str | None = None
    deadline_iso: str | None = None


class ExtractedTaskList(BaseModel):
    tasks: list[ExtractedTask]


class ReminderItem(BaseModel):
    reminder_text: str
    reminder_time_iso: str | None = None
    event_time_iso: str | None = None
    lead_description: str | None = None


class DispatchCommand(BaseModel):
    has_dispatch: bool
    is_reminder: bool = False
    is_settings: bool = False
    is_ghost: bool = False
    is_email: bool = False
    recipients: list[str] = []
    literal_message: str | None = None
    message_intent: str | None = None
    scheduled_at_iso: str | None = None
    # reminder-specific fields (single, kept for compat)
    reminder_text: str | None = None
    event_time_iso: str | None = None
    reminder_time_iso: str | None = None
    lead_description: str | None = None
    # multiple reminders
    reminder_items: list[ReminderItem] = []
    # settings-specific fields
    timezone_iana: str | None = None
    # ghost-specific fields
    ghost_active: bool = True
    ghost_away_message: str | None = None
    ghost_until_iso: str | None = None
    # email-specific fields
    email_subject: str | None = None
    email_body_intent: str | None = None
    email_literal_body: str | None = None
    email_has_attachment: bool = False
    # notion-specific fields
    is_notion: bool = False
    notion_action: str | None = None  # "capture" | "task" | "meeting_notes"
    notion_title: str | None = None
    notion_content: str | None = None
    notion_due_date_iso: str | None = None
    # google docs/sheets fields
    is_gdocs: bool = False
    gdocs_action: str | None = None  # "create_doc"|"append_doc"|"create_sheet"|"append_row"|"read_sheet"
    gdocs_target_name: str | None = None
    gdocs_content: str | None = None
    gdocs_row_values: list[str] | None = None


class ReminderAction(BaseModel):
    action: str  # "adjust_time" | "delete" | "none"
    reminder_hint: str | None = None
    new_reminder_time_iso: str | None = None
    lead_description: str | None = None


@beartype
async def extract_task_from_message(text: str, language: str = "ru", tz_name: str = "UTC") -> ExtractedTask:
    now = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%dT%H:%M:%S%z")
    lang_name = _LANG_NAMES.get(language, "Russian")
    client = _get_client()
    completion = await client.beta.chat.completions.parse(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Current local time ({tz_name}): {now}\n"
                    f"Respond in {lang_name}.\n"
                    "This message was sent BY the owner TO a contact. "
                    "Determine if the owner is DELEGATING a task — i.e. asking or expecting the contact to DO something specific.\n\n"
                    "Set has_task=TRUE only when ALL of these hold:\n"
                    "  1. There is a concrete action the CONTACT (not the owner) must perform.\n"
                    "  2. The message uses imperative, obligation, or explicit request directed at the other person "
                    "(e.g. 'пришли', 'сделай', 'подготовь', 'нужно тебе', 'не забудь').\n"
                    "  3. It is NOT the owner describing their own plans or status.\n\n"
                    "Set has_task=FALSE for:\n"
                    "  - Owner status updates: 'буду на месте в 16:30', 'еду', 'скоро приеду', 'жду тебя'\n"
                    "  - Confirmations and agreements: 'окей', 'договорились', 'хорошо', 'понял', 'до завтра'\n"
                    "  - Greetings, small talk, compliments\n"
                    "  - Sharing information without requiring action: 'встретимся в 10', 'завтра в офисе'\n"
                    "  - Owner's own commitments: 'я подготовлю', 'пришлю', 'позвоню'\n\n"
                    "If has_task=true, extract: description of what the contact must do, "
                    "deadline in ISO 8601 UTC if explicitly stated. "
                    f"Write description in {lang_name}."
                ),
            },
            {"role": "user", "content": text},
        ],
        response_format=ExtractedTask,
    )
    parsed = completion.choices[0].message.parsed
    return parsed if parsed is not None else ExtractedTask(has_task=False)


@beartype
async def extract_tasks_from_message(text: str, language: str = "ru", tz_name: str = "UTC") -> list[ExtractedTask]:
    """Extract ALL delegated tasks from a message. Returns empty list when none found."""
    now = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%dT%H:%M:%S%z")
    lang_name = _LANG_NAMES.get(language, "Russian")
    client = _get_client()
    completion = await client.beta.chat.completions.parse(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Current local time ({tz_name}): {now}\n"
                    f"Respond in {lang_name}.\n"
                    "This message was sent BY the owner TO a contact. "
                    "Extract ALL tasks being delegated — there may be more than one.\n\n"
                    "A task = a concrete action the CONTACT must perform "
                    "(imperative or obligation directed at them: 'пришли', 'сделай', 'подготовь').\n"
                    "NOT tasks: owner status updates ('буду там', 'еду'), "
                    "confirmations ('окей', 'договорились'), greetings, owner's own commitments ('я позвоню').\n\n"
                    "For each task set has_task=true, write a concise description of what the contact must do, "
                    "and set deadline_iso in ISO 8601 UTC if a deadline is explicitly stated. "
                    f"Write all descriptions in {lang_name}. "
                    "If no tasks are present return an empty list."
                ),
            },
            {"role": "user", "content": text},
        ],
        response_format=ExtractedTaskList,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        return []
    return [t for t in parsed.tasks if t.has_task and t.description]


@beartype
async def parse_dispatch_command(text: str, language: str = "ru", tz_name: str = "UTC") -> DispatchCommand:
    local_now = datetime.now(ZoneInfo(tz_name))
    now_str = local_now.strftime("%Y-%m-%dT%H:%M:%S%z")
    lang_name = _LANG_NAMES.get(language, "Russian")
    client = _get_client()
    completion = await client.beta.chat.completions.parse(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Current local time ({tz_name}): {now_str}\n"
                    f"Respond in {lang_name}.\n"
                    "Classify the message as one of two types:\n\n"
                    "TYPE A — DISPATCH: the owner wants to send a message to one or more people.\n"
                    "  Set has_dispatch=true, is_reminder=false.\n"
                    "  - recipients: list of contact names, ALWAYS normalized to Russian nominative case "
                    "(именительный падеж), first letter capitalized. "
                    "Examples: 'маме' → 'Мама', 'Диме' → 'Дима', 'Сашу' → 'Саша', 'папе' → 'Папа', "
                    "'брату' → 'Брат', 'Вовке' → 'Вова'. "
                    "If the name appears in quotes (e.g. «Мама», «Дима»), use the name inside the quotes.\n"
                    "  - literal_message: ONLY if the owner provides the exact text they want sent "
                    "(typically after the recipient, in quotes, or as a direct phrase). "
                    "IMPORTANT: a quoted word that identifies the RECIPIENT is NOT a literal_message — "
                    "e.g. 'Напиши «мама», приеду' → recipient='Мама', message_intent='приеду' (not literal). "
                    "When literal_message is set, leave message_intent null. Never rephrase literal text.\n"
                    "  - message_intent: if the owner describes what to convey without giving exact wording. "
                    "Leave null when literal_message is set.\n"
                    "  - scheduled_at_iso: send time in ISO 8601 with timezone offset if specified, else null.\n"
                    "  Common Russian patterns — always TYPE A:\n"
                    "    'Напиши маме привет' → recipient='Мама', literal_message='привет'\n"
                    "    'Напиши «мама», приеду' → recipient='Мама', message_intent='приеду'\n"
                    "    'Скажи Диме, что встреча в 6' → recipient='Дима', message_intent='встреча в 6'\n"
                    "    'Напомни Саше про отчёт' → recipient='Саша', message_intent='про отчёт'\n\n"
                    "TYPE B — REMINDER: the owner wants to be reminded of something at a future time "
                    "(no other recipients, the reminder is for themselves).\n"
                    "  Set is_reminder=true, has_dispatch=false, is_settings=false, recipients=[].\n"
                    "  IMPORTANT: if the message mentions MULTIPLE reminders or tasks, populate ALL of them "
                    "in reminder_items. For a single reminder, still put it in reminder_items as one entry.\n"
                    "  reminder_items fields per entry:\n"
                    "  - reminder_text: short self-explanatory description including event time if known "
                    "(e.g. 'стрижка в 15:00', 'встреча с Димой завтра в 18:00').\n"
                    "  - event_time_iso: time of the actual event in ISO 8601 with timezone offset. Null if none.\n"
                    "  - reminder_time_iso: when to SEND the reminder in ISO 8601 with timezone offset. "
                    "For relative times add EXACTLY that offset to current local time above. "
                    "If not specified: same-day event → 2 hours before; next-day → 09:00 that day; "
                    "no event time → 1 hour from now. Never equal to current time or event time.\n"
                    "  - lead_description: human-readable lead time in "
                    f"{lang_name} (e.g. 'за 2 часа', 'утром того дня'). Null if owner specified the time.\n"
                    "  Also copy the FIRST item's fields into top-level reminder_text/reminder_time_iso/"
                    "event_time_iso/lead_description for backward compatibility.\n\n"
                    "TYPE C — SETTINGS CHANGE: the owner wants to change a bot setting.\n"
                    "  Set is_settings=true, has_dispatch=false, is_reminder=false, is_ghost=false.\n"
                    "  - timezone_iana: if the owner mentions a new location or timezone (city, country, UTC offset), "
                    "resolve it to an IANA timezone string (e.g. 'Europe/Warsaw', 'America/New_York'). "
                    "Null if no timezone change is requested.\n\n"
                    "TYPE D — GHOST MODE: the owner is going offline/unavailable RIGHT NOW or imminently, "
                    "OR explicitly toggling ghost mode. "
                    "Examples: 'I'm in a meeting', 'я на встрече', 'I'm busy today', 'going offline', "
                    "'I'm free now', '/ghost off', 'turn off ghost mode', 'не беспокоить'.\n"
                    "  NOT TYPE D — these are TYPE B (reminder) or unclassified:\n"
                    "    'My doctor appointment was rescheduled from 6 to 8' → TYPE B\n"
                    "    'The meeting was moved to Thursday' → TYPE B or unclassified\n"
                    "    'Remind me about the doctor at 8' → TYPE B\n"
                    "  TYPE D requires the owner to be CURRENTLY or IMMEDIATELY going unavailable — "
                    "a future rescheduled event is never TYPE D.\n"
                    "  Set is_ghost=true, has_dispatch=false, is_reminder=false, is_settings=false.\n"
                    "  - ghost_active: true if they are becoming unavailable, false if they are free again.\n"
                    "  - ghost_away_message: when ghost_active=true:\n"
                    "      * If the owner provides explicit text to use as the away message "
                    "(e.g. after 'change message to:', 'автоответ:', 'use text:', or in quotes like «...»), "
                    "copy that text VERBATIM — never rephrase.\n"
                    "      * Otherwise compose a complete, natural away message in "
                    f"{lang_name}. Include: (1) that the person is unavailable, (2) the reason/time "
                    "if given, (3) an invitation to briefly describe their issue. "
                    "Example for 'meeting until 12': 'Сейчас на встрече, буду свободен около 12:00. "
                    "Если вопрос срочный — опишите кратко, отвечу как освобожусь.' "
                    "Keep it 1-2 sentences, natural, no emojis.\n"
                    "  - ghost_until_iso: if the owner mentions when they'll be free, the ISO 8601 datetime "
                    "with timezone offset at which ghost mode should auto-deactivate. Null otherwise.\n\n"
                    "IMPORTANT: TYPE D takes priority over TYPE B only when the owner is CURRENTLY "
                    "becoming unavailable. Rescheduling or updating a future appointment is TYPE B.\n\n"
                    "TYPE E — EMAIL: the owner wants to send an email to someone.\n"
                    "  Trigger phrases: 'отправь письмо', 'напиши email', 'пошли на почту', 'send email', "
                    "'написать email', 'email Диме', 'напиши письмо на почту'.\n"
                    "  Set is_email=true, has_dispatch=false, is_reminder=false, is_settings=false, is_ghost=false.\n"
                    "  - recipients: list of recipient names (same normalization as TYPE A).\n"
                    "  - email_subject: subject line if stated, else generate a short one from context.\n"
                    "  - email_literal_body: exact body text if owner provided it verbatim. Never rephrase.\n"
                    "  - email_body_intent: what to write if no exact body given. Null if literal_body is set.\n"
                    "  - email_has_attachment: true if owner mentions attaching a file/document/image.\n\n"
                    "TYPE F — NOTION: the owner wants to save something to Notion.\n"
                    "  Trigger phrases: 'запиши в ноушн', 'добавь в notion', 'заметка в ноушн', "
                    "'сохрани в ноушн', 'save to notion', 'добавь в ноушн', 'создай заметку'.\n"
                    "  Set is_notion=true, has_dispatch=false, is_reminder=false, is_email=false.\n"
                    "  - notion_action: one of 'capture' (quick note/idea), 'task' (to-do item with optional deadline), "
                    "'meeting_notes' (structured notes about a meeting/call).\n"
                    "    Use 'task' when owner says 'задача', 'добавь задачу', 'to-do', 'сделать'.\n"
                    "    Use 'meeting_notes' when owner says 'заметка о встрече', 'итоги встречи', 'конспект'.\n"
                    "    Default to 'capture' for everything else.\n"
                    "  - notion_title: short title for the entry (1 sentence max). Generate from context if not given.\n"
                    "  - notion_content: full content/body to save. Include all relevant details from the message.\n"
                    "  - notion_due_date_iso: for 'task' action only — deadline in ISO 8601 date format (YYYY-MM-DD). "
                    "Null if no deadline mentioned.\n\n"
                    "TYPE G — GOOGLE DOCS / SHEETS: the owner wants to work with Google Docs or Google Sheets.\n"
                    "  Trigger phrases: 'создай документ', 'сохрани в документ', 'добавь в таблицу', "
                    "'создай таблицу', 'покажи таблицу', 'записать в гугл документ', 'google doc', 'google sheet'.\n"
                    "  Set is_gdocs=true, has_dispatch=false, is_reminder=false, is_notion=false, is_email=false.\n"
                    "  - gdocs_action: one of:\n"
                    "      'create_doc' — create a new Google Doc.\n"
                    "      'append_doc' — add content to an existing doc (e.g. 'сохрани в документ X: текст').\n"
                    "      'create_sheet' — create a new Google Spreadsheet.\n"
                    "      'append_row' — add a row to a spreadsheet (e.g. 'добавь в таблицу расходов: кофе 200 руб').\n"
                    "      'read_sheet' — show recent rows from a spreadsheet.\n"
                    "  - gdocs_target_name: name of the document or spreadsheet (normalized: lowercase, spaces preserved).\n"
                    "  - gdocs_content: text content for doc operations. Null for sheet operations.\n"
                    "  - gdocs_row_values: for 'append_row' only — list of cell values as strings. "
                    "Always add today's date as the FIRST value (YYYY-MM-DD format). "
                    "Then split the data into logical cells. "
                    "Example: 'кофе 200 руб' → ['2024-01-15', 'кофе', '200', 'руб'].\n\n"
                    "If none of the above apply, set has_dispatch=false, is_reminder=false, is_settings=false, "
                    "is_ghost=false, is_email=false, is_notion=false, is_gdocs=false."
                ),
            },
            {"role": "user", "content": text},
        ],
        response_format=DispatchCommand,
    )
    parsed = completion.choices[0].message.parsed
    return parsed if parsed is not None else DispatchCommand(has_dispatch=False)


@beartype
async def generate_dispatch_message(
    intent: str,
    recipient_name: str | None,
    language: str = "ru",
    style_profile: str = "",
) -> str:
    lang_name = _LANG_NAMES.get(language, "Russian")
    context = f"Message to convey: {intent}"
    if recipient_name:
        context += f"\nRecipient: {recipient_name}"
    style_note = f"\n\nMatch this writing style exactly: {style_profile}" if style_profile else ""
    client = _get_client()
    completion = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are writing a short message in {lang_name} from a busy entrepreneur "
                    "to a colleague. Make it sound natural and personal — like the owner typed it "
                    "quickly themselves. One or two sentences max. No templates, no emojis at the "
                    f"start, no 'Dear ...'. Get to the point.{style_note}"
                ),
            },
            {"role": "user", "content": context},
        ],
        max_completion_tokens=120,
    )
    return (completion.choices[0].message.content or intent).strip()


@beartype
async def generate_nudge_message(
    description: str,
    assignee_name: str | None,
    deadline: datetime | None,
    language: str = "ru",
    style_profile: str = "",
) -> str:
    lang_name = _LANG_NAMES.get(language, "Russian")
    deadline_str = deadline.strftime("%d.%m.%Y %H:%M") if deadline else None

    context_parts = [f"Task: {description}"]
    if assignee_name:
        context_parts.append(f"Person: {assignee_name}")
    if deadline_str:
        context_parts.append(f"Deadline: {deadline_str}")

    style_note = f"\n\nMatch this writing style exactly: {style_profile}" if style_profile else ""
    client = _get_client()
    completion = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are writing a reminder message in {lang_name} on behalf of a busy entrepreneur "
                    "to a colleague or team member. "
                    "Write 1-2 sentences that sound natural and personal, as if a real person typed it quickly. "
                    "Do NOT use template phrases like 'Reminder:', 'Dear', emojis at the start, or bullet points. "
                    f"Keep it casual but professional. Vary the phrasing.{style_note}"
                ),
            },
            {"role": "user", "content": "\n".join(context_parts)},
        ],
        max_completion_tokens=120,
    )
    text = completion.choices[0].message.content or description
    return text.strip()


@beartype
async def generate_away_message(language: str = "ru") -> str:
    """Generate a polite away message for Ghost Mode."""
    from datetime import datetime, timezone
    lang_name = _LANG_NAMES.get(language, "Russian")
    hour = datetime.now(timezone.utc).hour
    time_hint = (
        "morning" if 5 <= hour < 12
        else "afternoon" if 12 <= hour < 18
        else "evening"
    )
    client = _get_client()
    completion = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Write a short, polite away message in {lang_name} for a busy entrepreneur. "
                    f"It is currently {time_hint}. "
                    "The message should: say they are currently unavailable, "
                    "invite the sender to briefly describe their request, "
                    "and note that they will respond as soon as possible. "
                    "Keep it to 1-2 sentences. No emojis. Natural and friendly tone."
                ),
            },
            {"role": "user", "content": "Generate an away message."},
        ],
        max_completion_tokens=100,
    )
    return (completion.choices[0].message.content or "").strip()


@beartype
async def extract_reminder_from_context(
    context_text: str,
    trigger_text: str,
    language: str = "ru",
    tz_name: str = "UTC",
) -> DispatchCommand:
    """Given a referenced message (context) and an owner trigger ('remind me'), extract a reminder."""
    local_now = datetime.now(ZoneInfo(tz_name))
    now_str = local_now.strftime("%Y-%m-%dT%H:%M:%S%z")
    lang_name = _LANG_NAMES.get(language, "Russian")
    client = _get_client()
    completion = await client.beta.chat.completions.parse(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Current local time ({tz_name}): {now_str}\n"
                    f"Respond in {lang_name}.\n"
                    "The owner wants a reminder based on the following chat message. "
                    "The owner's trigger may specify a time (e.g. 'remind me in 2 hours', 'tomorrow morning'); "
                    "if no time is given, pick a sensible default.\n\n"
                    "Return as TYPE B REMINDER:\n"
                    "  is_reminder=true, has_dispatch=false.\n"
                    "  - reminder_text: what to remind about, including key details from the context "
                    f"(e.g. 'позвонить Диме по вопросу договора'). In {lang_name}.\n"
                    "  - event_time_iso: event time if mentioned in context, in ISO 8601 with tz offset. Null if none.\n"
                    "  - reminder_time_iso: when to send the reminder. If owner specifies a time in the trigger, "
                    "use that. Otherwise pick a sensible lead: 2h before event if event_time given; "
                    "next morning (09:00) if the event is tomorrow or later; in 1 hour if no event time.\n"
                    "  - lead_description: human-readable description of the chosen lead time in "
                    f"{lang_name}. Null if the owner explicitly named the reminder time."
                ),
            },
            {
                "role": "user",
                "content": f"Chat message to remember:\n{context_text}\n\nOwner's trigger: {trigger_text}",
            },
        ],
        response_format=DispatchCommand,
    )
    parsed = completion.choices[0].message.parsed
    return parsed if parsed is not None else DispatchCommand(has_dispatch=False, is_reminder=True,
                                                              reminder_text=context_text[:80])


@beartype
async def parse_reminder_action(
    text: str,
    active_reminders_ctx: str,
    language: str = "ru",
    tz_name: str = "UTC",
) -> ReminderAction:
    """Detects adjust_time or delete actions against existing reminders."""
    local_now = datetime.now(ZoneInfo(tz_name))
    now_str = local_now.strftime("%Y-%m-%dT%H:%M:%S%z")
    lang_name = _LANG_NAMES.get(language, "Russian")
    client = _get_client()
    completion = await client.beta.chat.completions.parse(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Current local time ({tz_name}): {now_str}\n"
                    f"Active reminders:\n{active_reminders_ctx}\n\n"
                    f"Respond in {lang_name}.\n"
                    "Determine if the message is about an existing reminder. Two possible actions:\n\n"
                    "ACTION adjust_time: owner wants to change the time of a reminder.\n"
                    "  - reminder_hint: keyword identifying which reminder (e.g. 'haircut').\n"
                    "  - new_reminder_time_iso: new send time in ISO 8601 with timezone offset.\n"
                    "  - lead_description: human-readable in "
                    f"{lang_name} (e.g. 'за 1 час'). Null if owner gave explicit clock time.\n\n"
                    "ACTION delete: owner wants to cancel/delete a reminder.\n"
                    "  - reminder_hint: keyword identifying which reminder.\n\n"
                    "If neither applies, set action='none'."
                ),
            },
            {"role": "user", "content": text},
        ],
        response_format=ReminderAction,
    )
    parsed = completion.choices[0].message.parsed
    return parsed if parsed is not None else ReminderAction(action="none")


class _ClassifiedInquiry(BaseModel):
    category: str
    summary: str
    has_question: bool


@beartype
async def classify_inquiry(text: str, language: str = "ru") -> tuple[InquiryCategory, str, bool]:
    """Returns (category, one-line summary, has_question) for a ghost-mode inquiry message."""
    lang_name = _LANG_NAMES.get(language, "Russian")
    client = _get_client()
    completion = await client.beta.chat.completions.parse(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Respond in {lang_name}.\n"
                    "Classify the following message from a contact.\n\n"
                    "Categories:\n"
                    "  Urgent — time-sensitive issue requiring immediate action\n"
                    "  Sales — sales pitch, partnership proposal, or advertising\n"
                    "  Team — message from a team member or employee\n"
                    "  Spam — irrelevant, automated, or greeting-only message\n\n"
                    "Return:\n"
                    "  category: one of Urgent, Sales, Team, Spam\n"
                    f"  summary: one concise sentence in {lang_name} describing what they want "
                    "(use 'просто поздоровался' / 'just said hello' if it's only a greeting)\n"
                    "  has_question: true if the message contains an actual request, question, or "
                    "substantive content (not just a greeting or short phrase)"
                ),
            },
            {"role": "user", "content": text},
        ],
        response_format=_ClassifiedInquiry,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        return InquiryCategory.spam, text[:100], False
    try:
        cat = InquiryCategory(parsed.category)
    except ValueError:
        cat = InquiryCategory.spam
    return cat, parsed.summary, parsed.has_question


@beartype
async def summarize_inquiry(text: str, language: str = "ru") -> str:
    """Condenses a long inquiry into a single sentence."""
    if len(text) < 120:
        return text
    lang_name = _LANG_NAMES.get(language, "Russian")
    client = _get_client()
    completion = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Summarize the following message in one concise sentence in {lang_name}. "
                    "Keep the key ask or issue. No intro phrases."
                ),
            },
            {"role": "user", "content": text},
        ],
        max_completion_tokens=80,
    )
    return (completion.choices[0].message.content or text).strip()


@beartype
async def transcribe_voice(audio_bytes: bytes) -> str:
    """Transcribe a voice message (OGG/Opus) using OpenAI Whisper."""
    import io
    client = _get_client()
    buf = io.BytesIO(audio_bytes)
    buf.name = "audio.ogg"
    transcript = await client.audio.transcriptions.create(model="whisper-1", file=buf)
    return transcript.text.strip()


@beartype
async def generate_agenda_recommendation(context: str, language: str = "ru") -> str:
    """1-2 sentence agenda recommendation for the morning brief."""
    lang_name = _LANG_NAMES.get(language, "Russian")
    client = _get_client()
    completion = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a personal assistant. Based on the morning brief data below, "
                    f"write 1-2 sentences in {lang_name} recommending who to contact first "
                    "and why. Be specific and direct. No intro phrases, no emojis."
                ),
            },
            {"role": "user", "content": context},
        ],
        max_completion_tokens=100,
    )
    return (completion.choices[0].message.content or "").strip()


@beartype
async def generate_meeting_notes(raw_text: str, language: str = "ru") -> str:
    lang_name = _LANG_NAMES.get(language, "Russian")
    client = _get_client()
    completion = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Structure the following meeting notes in {lang_name}. "
                    "Format as: Participants, Key decisions, Action items (with owner if mentioned), Next steps. "
                    "Be concise. Use bullet points. Do not add information not present in the source."
                ),
            },
            {"role": "user", "content": raw_text},
        ],
    )
    return completion.choices[0].message.content or raw_text


@beartype
async def embed_text(text: str) -> list[float]:
    client = _get_client()
    response = await client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


@beartype
async def answer_from_context(
    query: str,
    messages: list[Message],
    language: str = "ru",
    name_map: dict[int, str] | None = None,
    tz_name: str = "UTC",
) -> str:
    lang_name = _LANG_NAMES.get(language, "Russian")
    tz = ZoneInfo(tz_name)
    context_lines: list[str] = []
    for msg in sorted(messages, key=lambda m: m.timestamp):
        if name_map and msg.sender_id and msg.sender_id in name_map:
            who = name_map[msg.sender_id]
        else:
            who = msg.sender_name or f"ID {msg.sender_id}"
        local_ts = msg.timestamp.astimezone(tz)
        when = local_ts.strftime("%d.%m %H:%M")
        context_lines.append(f"[{when}] {who}: {msg.text}")
    context = "\n".join(context_lines)
    client = _get_client()
    completion = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Respond in {lang_name}. Use Telegram HTML formatting: "
                    "<b>bold</b> for names and key facts, plain text otherwise. "
                    "No markdown asterisks.\n"
                    "You are a personal assistant answering questions about past conversations. "
                    "The context below contains relevant messages from the owner's chat history "
                    "with timestamps already converted to the owner's local timezone.\n"
                    "Rules:\n"
                    "- Always cite the date and time (from the timestamp in brackets) for each fact you state.\n"
                    "- Use bullet points when citing 2+ separate facts.\n"
                    "- If the answer isn't clearly present in the context, say so briefly.\n"
                    "- Keep the total response under 5 sentences or 5 bullets."
                ),
            },
            {
                "role": "user",
                "content": f"Question: {query}\n\nRelevant messages:\n{context}",
            },
        ],
        max_completion_tokens=400,
    )
    return (completion.choices[0].message.content or "").strip()
