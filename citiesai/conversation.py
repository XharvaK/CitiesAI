"""Multi-turn Ask conversation memory."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import config_dir


@dataclass
class ConversationTurn:
    role: str
    content: str
    sources: list[dict[str, Any]] = field(default_factory=list)


class ConversationStore:
    def __init__(self, path: Path | None = None, *, max_turns: int = 20) -> None:
        self._path = path or (config_dir() / "conversation.json")
        self._max_turns = max_turns
        self._lock = threading.Lock()
        self._turns: list[ConversationTurn] = []
        self._city_name: str = ""
        self._city_header: str = ""
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self._city_name = str(data.get("city_name", ""))
        self._city_header = str(data.get("city_header", ""))
        for row in data.get("turns", []):
            if isinstance(row, dict) and row.get("role") and row.get("content"):
                self._turns.append(
                    ConversationTurn(
                        role=str(row["role"]),
                        content=str(row["content"]),
                        sources=list(row.get("sources") or []),
                    )
                )

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "city_name": self._city_name,
            "city_header": self._city_header,
            "turns": [
                {"role": t.role, "content": t.content, "sources": t.sources} for t in self._turns
            ],
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_city_context(self, city_name: str, header: str) -> None:
        with self._lock:
            if city_name != self._city_name:
                self._city_name = city_name
                self._turns.clear()
            self._city_header = header
            self._save()

    def set_city_header(self, header: str) -> None:
        """Backward-compatible alias; prefer set_city_context with a city name."""
        self.set_city_context(header, header)

    def add_turn(self, role: str, content: str, *, sources: list[dict[str, Any]] | None = None) -> None:
        with self._lock:
            self._turns.append(ConversationTurn(role=role, content=content, sources=sources or []))
            if len(self._turns) > self._max_turns:
                self._turns = self._turns[-self._max_turns :]
            self._save()

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()
            self._save()

    def messages_for_llm(self) -> list[dict[str, str]]:
        with self._lock:
            messages: list[dict[str, str]] = []
            if self._city_header:
                messages.append(
                    {
                        "role": "user",
                        "content": f"[Current city context]\n{self._city_header}",
                    }
                )
                messages.append(
                    {
                        "role": "assistant",
                        "content": "Understood. I have the current city metrics.",
                    }
                )
            for turn in self._turns:
                messages.append({"role": turn.role, "content": turn.content})
            return messages


_store: ConversationStore | None = None


def get_conversation() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store
