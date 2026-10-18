from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import GameSession, Result, User
from ..schemas import FinishIn, JoinIn, JoinOut, ResultOut, SessionCreateIn, SessionOut
from ..security import get_current_user
from ..services.feedback import generate_feedback
from ..services.hub import hub, new_pairing_code

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _owned(db: Session, sid: str, user: User) -> GameSession:
    s = db.get(GameSession, sid)
    if not s or s.owner_id != user.id:
        raise HTTPException(404, "Session not found")
    return s


@router.post("", response_model=SessionOut, status_code=201)
def create_session(body: SessionCreateIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    s = GameSession(owner_id=user.id, game_id=body.game_id, mode=body.mode, workout=body.workout,
                    pairing_code=new_pairing_code(),
                    code_expires_at=now + timedelta(seconds=settings.pairing_code_ttl_seconds))
    db.add(s)
    db.commit()
    hub.get_or_create(s.id, s.mode)
    return SessionOut(session_id=s.id, pairing_code=s.pairing_code, expires_at=s.code_expires_at,
                      status=s.status, ws_path=f"/ws/sessions/{s.id}")


@router.post("/join", response_model=JoinOut)
async def join_session(body: JoinIn, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    s = db.scalar(select(GameSession).where(GameSession.pairing_code == body.code.upper(),
                                            GameSession.status.in_(["created", "paired"])))
    if not s or _aware(s.code_expires_at) < datetime.now(timezone.utc):
        raise HTTPException(404, "Invalid or expired pairing code")
    room = hub.get_or_create(s.id, s.mode)
    slot = room.assign_slot(user.id)
    if slot is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session is full")
    s.status = "paired"
    db.commit()
    await hub.broadcast(room, {"type": "PHONE_PAIRED", "session_id": s.id, "player_slot": slot,
                               "player_name": user.name})
    return JoinOut(session_id=s.id, player_slot=slot, game_id=s.game_id, mode=s.mode,
                   workout=s.workout, ws_path=f"/ws/sessions/{s.id}")


@router.get("/{sid}")
def get_session(sid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _owned(db, sid, user)
    room = hub.rooms.get(sid)
    return {"session_id": s.id, "status": s.status, "game_id": s.game_id, "mode": s.mode,
            "phones_connected": sorted(room.phones) if room else [],
            "cv_ready": room.cv_ready if room else {}}


@router.post("/{sid}/finish", response_model=ResultOut)
async def finish_session(sid: str, body: FinishIn, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    s = _owned(db, sid, user)
    if s.result:  # idempotent: TV retrying after a network blip gets the saved result
        r = s.result
    else:
        if s.status == "finished":
            raise HTTPException(409, "Session already finished")
        # Validation: duo player scores must be consistent with the reported total
        if body.players and sum(p.score for p in body.players) != body.score:
            raise HTTPException(422, "Player scores must sum to total score")
        feedback = generate_feedback(body.score, body.duration_sec, body.exercises, body.form_errors)
        r = Result(session_id=s.id, user_id=user.id, score=body.score, duration_sec=body.duration_sec,
                   players=[p.model_dump() for p in body.players], exercises=body.exercises,
                   form_errors=body.form_errors, feedback=feedback)
        s.status, s.finished_at = "finished", datetime.now(timezone.utc)
        db.add(r)
        db.commit()
    room = hub.rooms.get(sid)
    if room:
        await hub.broadcast(room, {"type": "RESULT_SAVED", "session_id": sid, "score": r.score,
                                   "feedback": r.feedback})
        room.state = "finished"
    return ResultOut.model_validate(r)
