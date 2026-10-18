from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    preferences: dict
    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SessionCreateIn(BaseModel):
    game_id: str = "dodge_arena"
    mode: Literal["solo", "duo"] = "solo"
    workout: str | None = None


class SessionOut(BaseModel):
    session_id: str
    pairing_code: str
    expires_at: datetime
    status: str
    ws_path: str


class JoinIn(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class JoinOut(BaseModel):
    session_id: str
    player_slot: int
    game_id: str
    mode: str
    workout: str | None
    ws_path: str


class PlayerResult(BaseModel):
    slot: int = Field(ge=1, le=2)
    score: int = Field(ge=0, le=1_000_000)


class FinishIn(BaseModel):
    score: int = Field(ge=0, le=1_000_000)
    duration_sec: float = Field(gt=0, le=4 * 3600)
    players: list[PlayerResult] = []
    exercises: dict[str, int] = {}       # e.g. {"squat": 12, "jumping_jack": 30}
    form_errors: dict[str, int] = {}     # e.g. {"shallow_squat": 4}


class ResultOut(BaseModel):
    session_id: str
    score: int
    duration_sec: float
    players: list
    exercises: dict
    form_errors: dict
    feedback: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class StatsOut(BaseModel):
    total_sessions: int
    total_score: int
    best_score: int
    total_minutes: float
    current_streak_days: int
    exercises_total: dict[str, int]
    achievements: list[str]
