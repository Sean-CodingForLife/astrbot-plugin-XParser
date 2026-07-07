from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AccessControlConfig:
    cooldown_seconds: int = 10
    same_tweet_cooldown_seconds: int = 120
    acl_mode: str = "off"
    allowed_group_ids: set[str] = field(default_factory=set)
    allowed_private_user_ids: set[str] = field(default_factory=set)
    blocked_group_ids: set[str] = field(default_factory=set)
    blocked_private_user_ids: set[str] = field(default_factory=set)


class AccessControl:
    def __init__(self, config: AccessControlConfig):
        self.config = config
        self._session_last_parse_at: dict[str, float] = {}
        self._session_tweet_last_parse_at: dict[tuple[str, str], float] = {}

    def check(self, event: Any, tweet_id: str) -> tuple[bool, str | None]:
        if not self.is_allowed(event):
            return False, "当前会话不在 XParser 允许解析范围内。"

        wait_seconds = self.cooldown_wait_seconds(event, tweet_id)
        if wait_seconds > 0:
            return False, f"解析冷却中，请 {wait_seconds} 秒后再试。"

        self.mark_parsed(event, tweet_id)
        return True, None

    def is_allowed(self, event: Any) -> bool:
        if self.config.acl_mode == "off":
            return True

        group_id = safe_id(event.get_group_id())
        user_id = safe_id(event.get_sender_id())
        is_group = bool(group_id)

        if is_group:
            allowed_ids = self.config.allowed_group_ids
            blocked_ids = self.config.blocked_group_ids
            target_id = group_id
        else:
            allowed_ids = self.config.allowed_private_user_ids
            blocked_ids = self.config.blocked_private_user_ids
            target_id = user_id

        if self.config.acl_mode == "whitelist":
            return not allowed_ids or target_id in allowed_ids
        if self.config.acl_mode == "blacklist":
            return target_id not in blocked_ids
        return True

    def cooldown_wait_seconds(self, event: Any, tweet_id: str) -> int:
        session_key = session_key_for_event(event)
        now = time.time()
        waits: list[float] = []

        if self.config.cooldown_seconds > 0:
            last_parse_at = self._session_last_parse_at.get(session_key)
            if last_parse_at is not None:
                waits.append(last_parse_at + self.config.cooldown_seconds - now)

        if self.config.same_tweet_cooldown_seconds > 0:
            last_tweet_parse_at = self._session_tweet_last_parse_at.get((session_key, tweet_id))
            if last_tweet_parse_at is not None:
                waits.append(last_tweet_parse_at + self.config.same_tweet_cooldown_seconds - now)

        return max(0, int(max(waits, default=0) + 0.999))

    def mark_parsed(self, event: Any, tweet_id: str) -> None:
        session_key = session_key_for_event(event)
        now = time.time()
        self._session_last_parse_at[session_key] = now
        self._session_tweet_last_parse_at[(session_key, tweet_id)] = now


def normalize_acl_mode(value: Any) -> str:
    mode = str(value or "关闭").strip().lower()
    aliases = {
        "关闭": "off",
        "off": "off",
        "白名单": "whitelist",
        "whitelist": "whitelist",
        "黑名单": "blacklist",
        "blacklist": "blacklist",
    }
    normalized = aliases.get(mode, mode)
    if normalized in {"off", "whitelist", "blacklist"}:
        return normalized
    return "off"


def normalize_id_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (str, int)):
        values = [value]
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return {str(item).strip() for item in values if str(item).strip()}


def safe_id(value: Any) -> str:
    return str(value or "").strip()


def session_key_for_event(event: Any) -> str:
    group_id = safe_id(event.get_group_id())
    if group_id:
        return f"group:{group_id}"
    return f"private:{safe_id(event.get_sender_id())}"
