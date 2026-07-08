from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot.api import logger

from .temp_media_registry import TempMediaRegistry


class TempMediaServer:
    def __init__(
        self,
        registry: TempMediaRegistry,
        *,
        base_url: str,
        path_prefix: str = "/xparser/media",
        enabled: bool = True,
    ):
        self.registry = registry
        self.base_url = (base_url or "").rstrip("/")
        self.path_prefix = "/" + path_prefix.strip("/")
        self.enabled = enabled
        self._route_ready = False
        self._route_path = f"{self.path_prefix}/{{token}}"

    def is_ready(self) -> bool:
        return self.enabled and self._route_ready and bool(self.base_url)

    async def setup(self, context: Any) -> None:
        if not self.enabled or self._route_ready:
            return

        route_adder = getattr(context, "add_web_route", None)
        if route_adder is None:
            logger.warning(
                "Temp media HTTP fallback disabled: current AstrBot context has no add_web_route"
            )
            return

        try:
            result = route_adder(
                "GET",
                self._route_path,
                self.handle_request,
            )
        except TypeError:
            result = route_adder(
                self._route_path,
                self.handle_request,
            )

        if hasattr(result, "__await__"):
            await result

        self._route_ready = True
        if self.base_url:
            logger.info(
                f"Temp media HTTP fallback route enabled at {self.base_url}{self._route_path}"
            )
        else:
            logger.info(
                "Temp media HTTP route registered, but temp_media_base_url is empty so URL fallback stays disabled"
            )

    def create_temp_url(
        self,
        file_path: Path,
        mime_type: str,
        *,
        ttl_seconds: int = 300,
        once: bool = False,
    ) -> str | None:
        if not self.is_ready():
            return None
        token = self.registry.create_entry(
            file_path,
            mime_type,
            ttl_seconds=ttl_seconds,
            once=once,
        )
        return f"{self.base_url}{self.path_prefix}/{token}"

    async def handle_request(self, request: Any) -> Any:
        token = None
        match_info = getattr(request, "match_info", None)
        if isinstance(match_info, dict):
            token = match_info.get("token")
        elif match_info is not None:
            token = getattr(match_info, "get", lambda *_: None)("token")

        if not token:
            return self._error_response(404, b"missing token")

        entry = self.registry.get_entry(token)
        if entry is None:
            return self._error_response(404, b"token missing or expired")

        file_path = Path(entry.file_path)
        if not file_path.is_file():
            self.registry.delete_entry(token)
            return self._error_response(404, b"file missing")

        body = file_path.read_bytes()
        if entry.once:
            self.registry.delete_entry(token)
        return {
            "status": 200,
            "body": body,
            "headers": {
                "Content-Type": entry.mime_type or "application/octet-stream",
                "Cache-Control": "no-store",
            },
        }

    @staticmethod
    def _error_response(status: int, body: bytes) -> dict[str, Any]:
        return {
            "status": status,
            "body": body,
            "headers": {"Content-Type": "text/plain; charset=utf-8"},
        }
