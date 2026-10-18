import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now():
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("usr"))
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GameSession(Base):
    __tablename__ = "game_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("session"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)  # TV account
    game_id: Mapped[str] = mapped_column(String(50))
    mode: Mapped[str] = mapped_column(String(20), default="solo")  # solo | duo
    workout: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="created")  # created|paired|playing|finished|expired
    pairing_code: Mapped[str] = mapped_column(String(8), index=True)
    code_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped["Result | None"] = relationship(back_populates="session", uselist=False)


class Result(Base):
    __tablename__ = "results"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("res"))
    session_id: Mapped[str] = mapped_column(ForeignKey("game_sessions.id"), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    duration_sec: Mapped[float] = mapped_column(Float)
    players: Mapped[list] = mapped_column(JSON, default=list)      # [{slot, score, ...}]
    exercises: Mapped[dict] = mapped_column(JSON, default=dict)    # {"squat": 12, ...}
    form_errors: Mapped[dict] = mapped_column(JSON, default=dict)  # {"knee_valgus": 3}
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    session: Mapped[GameSession] = relationship(back_populates="result")
