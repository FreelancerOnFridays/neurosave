Never run "npm run dev".
Use "npm run build" to check if code compiles or not
Always use Context7 when I need library/API documentation, code generation, setup or configuration steps without me having to explicitly ask.

# Python Development Rules

## Environment
- Use `uv` for dependency management
- Virtual environment must be in `.venv` directory
- Always run `uv sync` before executing code

## Type Safety
- All functions must have complete type annotations (parameters and return types)
- Use `from __future__ import annotations` at the top of every file
- Prefer `list[str]` over `List[str]` (modern syntax)
- Use `X | None` instead of `Optional[X]`
- No `Any` types unless absolutely necessary (and document why)

## Runtime Type Checking
- Use `beartype` decorator on all public functions
- Import pattern:
  from beartype import beartype
  
  @beartype
  def my_function(name: str, count: int) -> list[str]:
      ...

## Project Setup
When creating a new project:

uv init
uv add beartype
uv add --dev mypy pyright

## Running Code
Always run through uv:

uv run python script.py
uv run mypy .
uv run pyright

## pyproject.toml Settings
Include these settings:

[tool.mypy]
strict = true
python_version = "3.12"

[tool.pyright]
typeCheckingMode = "strict"
pythonVersion = "3.12"

## File Template
Every Python file should start with:

from __future__ import annotations
from beartype import beartype



Project Overview:
With a recent Telegram update, it is now possible to grant bots access to chats on a personal Telegram account. The bot operates via the Telegram API. It acts as a digital twin and personal assistant for entrepreneurs and managers, analyzing incoming messages in the background, managing tasks, and filtering out information noise. The bot is designed to save the user’s mental energy

Technology stack:
Python, Aiogram 3, PostgreSQL + pgvector, Taskiq Redis, for Mini App NextJS+Tailwind

External integrations (Phase 9+):
- Google Calendar API (`google-auth-oauthlib`, `google-api-python-client`)
- Notion API (`notion-client`)
- Gmail API (OAuth 2.0, `gmail.send` + `gmail.readonly` scopes)
- CRM: AmoCRM, Bitrix24 (pluggable adapter pattern in `services/crm/`)
- Telegram folder sync: Telethon MTProto userbot (separate from aiogram bot)
- OAuth tokens stored in `oauth_tokens` table; configs in `integration_configs` table


1. Task Manager (Task Tracking)
A module for automatically identifying and tracking tasks from current conversations.

Context scanning: AI analyzes incoming and outgoing messages. If a task is detected in the text (e.g., “design the interface” or “review the report by 12 tomorrow”), the bot records the task (if technically possible, the bot should react to the message with an emoji [pen in hand]).

Task Log: Saving the task details, the person responsible, and the deadline to the database.

Proactive Notifications: A certain amount of time before the deadline, the bot sends a push notification to the owner.

Interactive engagement: Offer the owner the option to “nudge” the assignee with a single click (sending a polite reminder on behalf of the main account).

2. Ghost Mode (Smart Auto-Responder)
A mode for filtering incoming requests when the owner is busy or offline.

Automatic replies: The bot responds to messages from contacts (excluding the VIP list), informing them that the owner is busy.

Information Gathering: The assistant asks the caller to briefly summarize the issue so that the information can be relayed to the owner.

Classification and Prioritization: The AI analyzes the responses and sorts them into categories: “Urgent,” “Sales Pitch,” “Team Inquiry,” “Spam.”

Missed Messages Digest: The owner receives a structured list of those who have written, with a brief summary of their requests.

3. Instant Context (External Memory)
A system for quickly searching and retrieving context from the entire chat history.

Natural Language Queries: The owner can ask the assistant in the chat: “What did we agree on with Dima last week regarding the commission?”

Summary of Responses: Instead of displaying hundreds of messages, the bot generates a concise response based on the facts found, saving time on manual searches.

4. Morning Coffee Brief (Daily Dashboard)
A daily structured report to prepare for the workday.

Frequency: Sent automatically every morning at a set time (e.g., 9:00 AM).

Brief contents:

Hot Tasks: A list of tasks with deadlines falling today.

Team Status: A report on employees’ overdue tasks from the previous day.

Night Digest: A brief summary of important messages received while the owner was asleep.

Agenda: A recommendation on who to contact first.

5. A feature for adding reminders and tasks. 
For example, you can tell the assistant, “Remind me that I have a haircut at 6 p.m. tomorrow,” or “Send a message to Vova at 5 p.m. on May 20 inviting him to my birthday party.”

6. A feature that allows users to control the assistant by sending voice messages. The bot should listen to the voice messages sent by users, analyze their requests, and carry them out. 

7. Create a daily schedule in the morning based on your set reminders. You can also edit the schedule and add or remove tasks as you complete them.

8.Migrating from the bot's command interface to a convenient, user-friendly Telegram mini-app. However, you can still control the assistant via chat with the bot. The mini-app makes it easier to view tasks, reminders, settings, and more.

---

## Development Status (updated 2026-05-17)

### ✅ Complete
- **Phase 1** — Foundation: bot skeleton, DB models, middleware, config, migrations
- **Phase 2** — Task Manager: auto-extraction from business messages, task DB, deadline reminders, nudge via callback keyboard
- **Phase 2** — Dispatch & Scheduling: owner sends messages to contacts by name, scheduled sends (“in 10 minutes”), contact aliases (`saved_name`), `has_business_chat` guard
- **Phase 2 Polish** — Style Profiling: `extract_style_profile` + `get_style_profile` (1h cache) injected into `generate_dispatch_message` and `generate_nudge_message`
- **Dispatch AI fix** — `literal_message` passthrough in `direct_messages.py`
- **Phase 6** — Personal reminders: DB-backed tasks with `reminder_time`, polling worker `workers/reminder_worker.py`
- **Phase 3** — Ghost Mode: auto-responder, `classify_inquiry`, VIP bypass, AI summaries, digest, silent mode
- **Phase 4** — Instant Context / RAG: `embed_text`, `search_similar`, `answer_from_context`, `/ask`
- **Phase 5** — Morning Coffee Brief: `workers/morning_brief.py`, hot tasks + overdue + night digest + reminders + AI agenda
- **Phase 8** — Mini-App: NextJS + Tailwind Telegram Mini App with Today/Tasks/Ghost/Settings tabs, Framer Motion animations, swipe actions, theme sync, SegmentedControl, FilterBar, TimePickerSheet, InfoTooltip; OAuth-ready API layer
- **Phase 9** — External Integrations:
  - OAuth infrastructure: `oauth_tokens` + `integration_configs` tables, `/api/integrations/` router, token refresh worker
  - Google Calendar: OAuth 2.0, task deadline → calendar event sync, calendar view in mini-app
  - Gmail: OAuth, send email by name, file attachments from TG, email preview + inline edit/cancel, email persistence via `integration_configs`
  - Notion: capture notes/tasks/meetings with section routing, custom folder names, markdown formatting toolbar
  - Google Docs/Sheets: create and list recent documents from mini-app
  - Telegram folder sync: Telethon MTProto userbot, `/sync_contacts` + folder sync from mini-app
- **Phase 10** — UX Improvements & Integrations polish:
  - **10A** — Task cancel: DM to owner after task extraction with ❌ inline button → sets `status=cancelled`
  - **10B** — Gmail reply forwarding: `workers/gmail_reply_worker.py` polls inbox history every 5 min, forwards new replies as bot DMs
  - **10C** — Settings cleanup: removed duplicate Notion quick-capture from Settings (lives in Services tab only)
  - **10D** — Gmail workspace in Services tab: thread list (sent + inbox), “Входящий ответ” badge, compose deep-link
  - **10E** — Notion workspace improvements: markdown formatting toolbar (B/I/H1/H2/list/checkbox/code), custom section/folder names via `integration_configs`
  - **10F** — Contacts screen: `/contacts` page with avatars (proxied via Bot API), search, edit `saved_name` + email; “Все контакты” button in Settings

