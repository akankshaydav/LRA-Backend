"""In-memory real-time hub: one 'room' per session. Single-process; for multiple
workers/instances, swap for Redis pub/sub (not needed for the hackathon MVP)."""
import secrets
import string
from dataclasses import dataclass, field

from fastapi import WebSocket

_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1")


def new_pairing_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(6))


@dataclass
class Room:
    session_id: str
    mode: str
    tv: WebSocket | None = None
    phones: dict[int, WebSocket] = field(default_factory=dict)        # slot -> ws
    phone_users: dict[str, int] = field(default_factory=dict)         # user_id -> slot
    last_seq: dict[int, int] = field(default_factory=dict)            # slot -> last sequence
    cv_ready: dict[int, bool] = field(default_factory=dict)
    scores: dict[int, int] = field(default_factory=dict)
    state: str = "waiting"  # waiting | ready | playing | finished

    @property
    def max_players(self) -> int:
        return 2 if self.mode == "duo" else 1

    def assign_slot(self, user_id: str) -> int | None:
        if user_id in self.phone_users:
            return self.phone_users[user_id]
        for slot in range(1, self.max_players + 1):
            if slot not in self.phone_users.values():
                self.phone_users[user_id] = slot
                return slot
        return None

    def all_ready(self) -> bool:
        return len(self.cv_ready) >= self.max_players and all(self.cv_ready.values())


class Hub:
    def __init__(self):
        self.rooms: dict[str, Room] = {}

    def get_or_create(self, session_id: str, mode: str) -> Room:
        return self.rooms.setdefault(session_id, Room(session_id, mode))

    def drop(self, session_id: str):
        self.rooms.pop(session_id, None)

    @staticmethod
    async def _send(ws: WebSocket | None, msg: dict):
        if ws is None:
            return
        try:
            await ws.send_json(msg)
        except Exception:
            pass  # dead sockets are cleaned up by their receive loop

    async def to_tv(self, room: Room, msg: dict):
        await self._send(room.tv, msg)

    async def to_phones(self, room: Room, msg: dict):
        for ws in list(room.phones.values()):
            await self._send(ws, msg)

    async def broadcast(self, room: Room, msg: dict):
        await self.to_tv(room, msg)
        await self.to_phones(room, msg)


hub = Hub()
