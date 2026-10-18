import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402
from app.main import app  # noqa: E402
from app.db import Base, engine  # noqa: E402


def reg(c, email):
    r = c.post("/api/v1/auth/register",
               json={"name": email[:3], "email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, tok


def wait_for(ws, wanted, limit=10):
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == wanted:
            return msg
    raise AssertionError(f"never received {wanted}")


def test_full_journey():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        tv_h, tv_tok = reg(c, "tv@x.com")
        ph_h, ph_tok = reg(c, "phone@x.com")
        s = c.post("/api/v1/sessions", json={"game_id": "dodge_arena"}, headers=tv_h).json()
        j = c.post("/api/v1/sessions/join", json={"code": s["pairing_code"]}, headers=ph_h).json()
        assert j["player_slot"] == 1
        sid = s["session_id"]

        with c.websocket_connect(f"/ws/sessions/{sid}?token={tv_tok}&role=tv") as tv:
            wait_for(tv, "CONNECTED")
            with c.websocket_connect(f"/ws/sessions/{sid}?token={ph_tok}&role=phone") as ph:
                wait_for(ph, "CONNECTED")
                wait_for(tv, "PHONE_PAIRED")
                ph.send_json({"type": "CV_READY", "ready": True})
                wait_for(tv, "ALL_READY")
                wait_for(ph, "ALL_READY")
                tv.send_json({"type": "GAME_STARTED"})
                wait_for(ph, "GAME_STARTED")
                ph.send_json({"type": "PLAYER_ACTION", "action": "JUMP", "sequence": 1})
                assert wait_for(tv, "PLAYER_ACTION")["sequence"] == 1
                ph.send_json({"type": "PLAYER_ACTION", "action": "JUMP", "sequence": 1})  # dup
                ph.send_json({"type": "PLAYER_ACTION", "action": "DUCK", "sequence": 2})
                nxt = wait_for(tv, "PLAYER_ACTION")
                assert nxt["sequence"] == 2 and nxt["action"] == "DUCK"  # dup was dropped

        r = c.post(f"/api/v1/sessions/{sid}/finish", headers=tv_h,
                   json={"score": 120, "duration_sec": 90, "exercises": {"squat": 10},
                         "form_errors": {"shallow_squat": 3}})
        assert r.status_code == 200 and r.json()["feedback"]
        assert c.get("/api/v1/profile/stats", headers=tv_h).json()["total_sessions"] == 1

        _, other_tok = reg(c, "evil@x.com")
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect(f"/ws/sessions/{sid}?token={other_tok}&role=phone") as ws:
                ws.receive_json()
