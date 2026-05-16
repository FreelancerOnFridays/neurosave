from __future__ import annotations

import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, Text, func, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TaskStatus(str, enum.Enum):
    open = "open"
    done = "done"
    cancelled = "cancelled"


class InquiryCategory(str, enum.Enum):
    urgent = "Urgent"
    sales = "Sales"
    team = "Team"
    spam = "Spam"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assignee_name: Mapped[str | None] = mapped_column(String(256))
    assignee_user_id: Mapped[int | None] = mapped_column(BigInteger)
    assignee_username: Mapped[str | None] = mapped_column(String(256))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    business_connection_id: Mapped[str | None] = mapped_column(String(256))
    reminder_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_personal: Mapped[bool] = mapped_column(default=False, nullable=False)
    reminder_fired: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.open, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_id: Mapped[int | None] = mapped_column(BigInteger)
    sender_name: Mapped[str | None] = mapped_column(String(256))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str | None] = mapped_column(String(256))
    username: Mapped[str | None] = mapped_column(String(256))
    saved_name: Mapped[str | None] = mapped_column(String(256))
    has_business_chat: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_vip: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone: Mapped[str | None] = mapped_column(String(32))
    team_label: Mapped[str | None] = mapped_column(String(64))
    synced_from: Mapped[str | None] = mapped_column(String(32))
    tg_first_name: Mapped[str | None] = mapped_column(String(128))
    tg_last_name: Mapped[str | None] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(255))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GhostSession(Base):
    __tablename__ = "ghost_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=False, nullable=False)
    away_message: Mapped[str | None] = mapped_column(Text)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    silent_mode: Mapped[bool] = mapped_column(default=False, nullable=False)


class UserSettings(Base):
    __tablename__ = "user_settings"

    owner_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    language: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", nullable=False)
    brief_time: Mapped[str] = mapped_column(String(8), default="09:00", nullable=False)
    brief_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    theme: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)
    telethon_session: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntegrationConfig(Base):
    __tablename__ = "integration_configs"

    owner_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GhostInquiry(Base):
    __tablename__ = "ghost_inquiries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    caller_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    caller_name: Mapped[str | None] = mapped_column(String(256))
    caller_username: Mapped[str | None] = mapped_column(String(256))
    summary: Mapped[str | None] = mapped_column(Text)
    category: Mapped[InquiryCategory | None] = mapped_column(
        Enum(InquiryCategory, values_callable=lambda obj: [e.value for e in obj])
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ghost_pending: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
