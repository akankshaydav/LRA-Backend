from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Result, User
from ..schemas import ResultOut, StatsOut, UserOut
from ..security import get_current_user

router = APIRouter(prefix="/api/v1", tags=["users"])

GAMES = [
    {"id": "dodge_arena", "name": "Dodge Arena", "modes": ["solo", "duo"],
     "controls": ["JUMP", "DUCK", "MOVE_LEFT", "MOVE_RIGHT"]},
    {"id": "fitness_quest", "name": "Fitness Quest", "modes": ["solo", "duo"],
     "controls": ["SQUAT", "JUMPING_JACK"]},
]
WORKOUTS = [
    {"id": "chest_day", "name": "Chest Day"}, {"id": "leg_day", "name": "Leg Day"},
    {"id": "full_body", "name": "Full Body"}, {"id": "skill_training", "name": "Skill Training"},
]


@router.get("/users/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/preferences")
def get_prefs(user: User = Depends(get_current_user)):
    return user.preferences or {}


@router.patch("/preferences")
def patch_prefs(prefs: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.preferences = {**(user.preferences or {}), **prefs}
    db.add(user)
    db.commit()
    return user.preferences


@router.get("/games")
def games():
    return GAMES


@router.get("/workouts")
def workouts():
    return WORKOUTS


@router.get("/history", response_model=list[ResultOut])
def history(limit: int = 20, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Result).where(Result.user_id == user.id)
                      .order_by(Result.created_at.desc()).limit(min(limit, 100))).all()
    return [ResultOut(session_id=r.session_id, score=r.score, duration_sec=r.duration_sec,
                      players=r.players, exercises=r.exercises, form_errors=r.form_errors,
                      feedback=r.feedback, created_at=r.created_at) for r in rows]


@router.get("/profile/stats", response_model=StatsOut)
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Result).where(Result.user_id == user.id)).all()
    totals: dict[str, int] = {}
    for r in rows:
        for k, v in (r.exercises or {}).items():
            totals[k] = totals.get(k, 0) + v
    days = {r.created_at.date() for r in rows}
    streak, d = 0, date.today()
    if d not in days:
        d -= timedelta(days=1)
    while d in days:
        streak += 1
        d -= timedelta(days=1)
    ach = []
    if rows: ach.append("First Session")
    if len(rows) >= 10: ach.append("10 Sessions")
    if totals.get("squat", 0) >= 100: ach.append("100 Squats")
    if streak >= 3: ach.append("3-Day Streak")
    return StatsOut(total_sessions=len(rows), total_score=sum(r.score for r in rows),
                    best_score=max((r.score for r in rows), default=0),
                    total_minutes=round(sum(r.duration_sec for r in rows) / 60, 1),
                    current_streak_days=streak, exercises_total=totals, achievements=ach)


@router.get("/achievements")
def achievements(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"achievements": stats(user, db).achievements}
