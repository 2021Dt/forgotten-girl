from __future__ import annotations

from typing import Dict

from .models import GameState


class InMemoryStore:
    def __init__(self) -> None:
        self._store: Dict[str, GameState] = {}

    def get(self, session_id: str) -> GameState:
        return self._store[session_id]

    def save(self, state: GameState) -> None:
        self._store[state.session_id] = state

    def exists(self, session_id: str) -> bool:
        return session_id in self._store
