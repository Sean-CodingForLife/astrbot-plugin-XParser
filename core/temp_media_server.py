from __future__ import annotations

from pathlib import Path

from aiohttp import web
from astrbot.api import logger

from .temp_media_registry import TempMediaRegistry


class TempMediaServer:
    def __init__(
        self,
        registry: TempMediaRegistry,
        *,
        base_url: str,
        path_prefix: str = "/xparser/media",
        host: str = "0.0.0.0",
        port: int = 6190,
        enabled: bool = True,
    ):
        self.registry = registry
        self.base_url = (base_url or "").rstrip("/")
        self.path_prefix = "/" + path_prefix.strip("/")
        self.host = (host or "0.0.0.0").strip() or "0.0.0.0"
        self.port = max(1, int(port))
        self.enabled = enabled
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._route_ready = False

    def is_ready(self) -> bool:
        return self.enabled and self._route_ready and bool(self.base_url)

    async def setup(self) -> None:
        if not self.enabled or self._route_ready:
            return

        app = web.Application()
        app.router.add_get(f"{self.path_prefix}/{{token}}", self.handle_request)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        self._app = app
        self._runner = runner
        self._site = site
        self._route_ready = True
        logger.info(
            "Temp media HTTP server started at "
            f"{self.host}:{self.port}, external base URL: {self.base_url}{self.path_prefix}/<token>"
        )

    async def close(self) -> None:
        self._route_ready = False
        site = self._site
        runner = self._runner
        self._site = None
        self._runner = None
        self._app = None

        if site is not None:
            await site.stop()
        if runner is not None:
            await runner.cleanup()

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

    async def handle_request(self, request: web.Request) -> web.StreamResponse:
        token = request.match_info.get("token", "")
        if not token:
            raise web.HTTPNotFound(text="missing token")

        entry = self.registry.get_entry(token)
        if entry is None:
            raise web.HTTPNotFound(text="token missing or expired")

        file_path = Path(entry.file_path)
        if not file_path.is_file():
            self.registry.delete_entry(token)
            raise web.HTTPNotFound(text="file missing")

        response = web.FileResponse(file_path)
        response.headers["Content-Type"] = (
            entry.mime_type or "application/octet-stream"
        )
        response.headers["Cache-Control"] = "no-store"
        if entry.once:
            self.registry.delete_entry(token)
        return response
