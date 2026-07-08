from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TempMediaEntry:
    file_path: Path
    mime_type: str
    expires_at: float
    once: bool = False


class TempMediaRegistry:
    def __init__(self):
        self._entries: dict[str, TempMediaEntry] = {}

    def create_entry(
        self,
        file_path: Path,
        mime_type: str,
        *,
        ttl_seconds: int = 300,
        once: bool = False,
    ) -> str:
        self.cleanup_expired()
        token = secrets.token_urlsafe(24)
        self._entries[token] = TempMediaEntry(
            file_path=Path(file_path),
            mime_type=mime_type,
            expires_at=time.time() + max(1, ttl_seconds),
            once=once,
        )
        return token

    def get_entry(self, token: str) -> TempMediaEntry | None:
        entry = self._entries.get(token)
        if entry is None:
            return None
        if entry.expires_at < time.time():
            self._entries.pop(token, None)
            return None
        return entry

    def delete_entry(self, token: str) -> None:
        self._entries.pop(token, None)

    def cleanup_expired(self) -> int:
        now = time.time()
        expired_tokens = [
            token for token, entry in self._entries.items() if entry.expires_at < now
        ]
        for token in expired_tokens:
            self._entries.pop(token, None)
        return len(expired_tokens)
