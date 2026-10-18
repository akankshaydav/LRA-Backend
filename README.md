# Living Room Arena — Backend (FastAPI)

Auth, profiles, pairing/sessions, real-time WebSocket relay (phone → TV), score sync,
result persistence (PostgreSQL) and AI feedback.

## Run
    cp .env.example .env
    docker compose up --build          # API on :8000, Postgres on :5432
    # or locally: pip install -r requirements.txt && uvicorn app.main:app --reload
Docs: http://localhost:8000/docs · Tests: `pytest`

## Flow
1. TV: `POST /api/v1/auth/register|login` → JWT
2. TV: `POST /api/v1/sessions {game_id, mode}` → `pairing_code` (expires in 5 min), show as QR/code
3. Phone: login, `POST /api/v1/sessions/join {code}` → `session_id`, `player_slot`
4. Both open `ws://HOST/ws/sessions/{id}?token=JWT&role=tv|phone`
5. Phone sends `CAMERA_READY`, `CV_READY`; server emits `ALL_READY` → TV enables Start
6. TV sends `GAME_STARTED`; phone sends `{"type":"PLAYER_ACTION","action":"JUMP","sequence":N}`;
   duplicates/out-of-order sequences are dropped; TV sends `SCORE_UPDATE {slot,score}` → phones get `SCORE_SYNC`
7. TV: `POST /api/v1/sessions/{id}/finish {score, duration_sec, players, exercises, form_errors}`
   → validated, saved, AI feedback generated, `RESULT_SAVED` broadcast

Other endpoints: `GET /users/me`, `/games`, `/workouts`, `/history`, `/profile/stats`,
`/achievements`, `GET|PATCH /preferences`.

## Notes
- Sessions are paired via an expiring code, and WebSockets require a JWT of the session owner (TV)
  or a joined phone — arbitrary LAN clients can't inject actions.
- Hub state is in-memory (single process). Use Redis pub/sub if you ever scale to multiple workers.
- Replace `create_all` with Alembic migrations when the schema stabilizes.
- Set `ANTHROPIC_API_KEY` for Claude-written feedback; otherwise rule-based tips are used.
