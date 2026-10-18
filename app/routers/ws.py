"""Real-time channel. Connect: ws://host/ws/sessions/{id}?token=<JWT>&role=tv|phone

Authenticated: the TV must be the session owner; a phone must have joined via the pairing
code (POST /sessions/join) so we never trust arbitrary LAN clients.

Phone -> server: CAMERA_READY, CV_READY {ready}, PLAYER_ACTION {action, sequence}, FORM_ERROR {error}, PING
TV    -> server: GAME_STARTED, SCORE_UPDATE {slot, score}, GAME_FINISHED, PING
Server -> clients: PHONE_PAIRED, CAMERA_READY, CV_READY, ALL_READY, PLAYER_ACTION, SCORE_SYNC,
                   GAME_STARTED, GAME_FINISHED, PHONE_DISCONNECTED, ERROR, PONG
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import GameSession
from ..security import decode_token
from ..services.hub import hub

router = APIRouter()
log = logging.getLogger(__name__)
ACTIONS = {"JUMP", "DUCK", "MOVE_LEFT", "MOVE_RIGHT", "SQUAT", "JUMPING_JACK", "POSE_HOLD"}


@router.websocket("/ws/sessions/{sid}")
async def session_ws(ws: WebSocket, sid: str, token: str = "", role: str = "phone"):
    uid = decode_token(token)
    db: Session = SessionLocal()
    try:
        s = db.get(GameSession, sid)
        if not uid or not s or role not in ("tv", "phone"):
            await ws.close(code=4401)
            return
        room = hub.get_or_create(sid, s.mode)
        slot = 0
        if role == "tv":
            if s.owner_id != uid:
                await ws.close(code=4403)
                return
        else:
            slot = room.phone_users.get(uid, 0)
            if not slot:
                await ws.close(code=4403)  # hasn't joined with a valid code
                return
    finally:
        db.close()

    await ws.accept()
    if role == "tv":
        room.tv = ws
        for sl in room.phones:  # tell TV who's already here
            await ws.send_json({"type": "PHONE_PAIRED", "session_id": sid, "player_slot": sl})
    else:
        room.phones[slot] = ws
        room.last_seq[slot] = 0
        await hub.to_tv(room, {"type": "PHONE_PAIRED", "session_id": sid, "player_slot": slot})
    await ws.send_json({"type": "CONNECTED", "role": role, "player_slot": slot, "session_id": sid})

    try:
        while True:
            msg = await ws.receive_json()
            await _handle(room, ws, role, slot, msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("ws error: %s", e)
    finally:
        if role == "tv" and room.tv is ws:
            room.tv = None
        elif role == "phone" and room.phones.get(slot) is ws:
            room.phones.pop(slot, None)
            room.cv_ready.pop(slot, None)
            await hub.to_tv(room, {"type": "PHONE_DISCONNECTED", "player_slot": slot})


async def _handle(room, ws, role, slot, msg: dict):
    t = msg.get("type")
    sid = room.session_id
    if t == "PING":
        await ws.send_json({"type": "PONG"})
    elif role == "phone" and t == "PLAYER_ACTION":
        action, seq = msg.get("action"), msg.get("sequence")
        if action not in ACTIONS or not isinstance(seq, int):
            await ws.send_json({"type": "ERROR", "detail": "bad PLAYER_ACTION"})
        elif seq <= room.last_seq.get(slot, 0):
            return  # duplicate / replay / out-of-order: drop silently
        elif room.state != "playing":
            return  # ignore actions outside gameplay
        else:
            room.last_seq[slot] = seq
            await hub.to_tv(room, {"type": "PLAYER_ACTION", "session_id": sid, "player_slot": slot,
                                   "action": action, "sequence": seq})
    elif role == "phone" and t in ("CAMERA_READY", "CV_READY"):
        ready = bool(msg.get("ready", True))
        if t == "CV_READY":
            room.cv_ready[slot] = ready
        await hub.to_tv(room, {"type": t, "player_slot": slot, "ready": ready})
        if t == "CV_READY" and room.all_ready():
            room.state = "ready"
            await hub.broadcast(room, {"type": "ALL_READY", "session_id": sid})
    elif role == "phone" and t == "FORM_ERROR":
        await hub.to_tv(room, {"type": "FORM_ERROR", "player_slot": slot,
                               "error": str(msg.get("error", ""))[:50],
                               "joint": str(msg.get("joint", ""))[:30]})
    elif role == "tv" and t == "GAME_STARTED":
        if room.state != "ready" and msg.get("require_ready", True):
            await ws.send_json({"type": "ERROR", "detail": "Not all players CV_READY"})
            return
        room.state = "playing"
        room.scores = {sl: 0 for sl in range(1, room.max_players + 1)}
        await hub.broadcast(room, {"type": "GAME_STARTED", "session_id": sid})
    elif role == "tv" and t == "SCORE_UPDATE":
        sl, sc = msg.get("slot"), msg.get("score")
        if isinstance(sl, int) and isinstance(sc, int) and sc >= 0 and sl in range(1, room.max_players + 1):
            room.scores[sl] = sc
            await hub.to_phones(room, {"type": "SCORE_SYNC", "scores": room.scores})
    elif role == "tv" and t == "GAME_FINISHED":
        room.state = "finished"
        await hub.to_phones(room, {"type": "GAME_FINISHED", "scores": room.scores})
    else:
        await ws.send_json({"type": "ERROR", "detail": f"unsupported message {t!r} for {role}"})
