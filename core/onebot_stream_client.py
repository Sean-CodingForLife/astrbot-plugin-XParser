from __future__ import annotations

import base64
import hashlib
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from astrbot.api import logger


class NapCatStreamClient:
    """Small wrapper around NapCat's Stream API actions.

    AstrBot's aiocqhttp adapter exposes the underlying OneBot client on
    ``event.bot``.  NapCat action wrappers vary by adapter version, so this
    class tries the explicit stream method first and then falls back to a raw
    ``call_action`` style invocation.
    """

    def __init__(self, max_bytes: int = 100 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.chunk_size = 512 * 1024

    @staticmethod
    def is_aiocqhttp_event(event: Any) -> bool:
        try:
            if event.get_platform_name() == "aiocqhttp":
                return True
        except Exception:
            pass
        return getattr(getattr(event, "platform_meta", None), "name", "") == "aiocqhttp"

    async def upload_file_stream(
        self,
        event: Any,
        file_path: Path,
        *,
        name: str | None = None,
        folder: str = "/",
    ) -> str | None:
        if not self.is_aiocqhttp_event(event):
            return None

        bot = getattr(event, "bot", None)
        if bot is None:
            logger.warning("NapCat Stream upload skipped: current event has no bot client")
            return None

        file_path = Path(file_path)
        if not file_path.is_file():
            logger.warning(f"NapCat Stream upload skipped, file missing: {file_path}")
            return None

        size = file_path.stat().st_size
        if size <= 0 or size > self.max_bytes:
            logger.warning(
                "NapCat Stream upload skipped, file size out of bounds: "
                f"{file_path} ({size} bytes)"
            )
            return None

        file_name = name or file_path.name
        mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        data = file_path.read_bytes()
        expected_sha256 = hashlib.sha256(data).hexdigest()
        stream_id = uuid.uuid4().hex
        total_chunks = (size + self.chunk_size - 1) // self.chunk_size

        final_result: Any = None

        try:
            for chunk_index in range(total_chunks):
                start = chunk_index * self.chunk_size
                chunk = data[start : start + self.chunk_size]
                payload = {
                    "stream_id": stream_id,
                    "chunk_data": base64.b64encode(chunk).decode("ascii"),
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks,
                    "file_size": size,
                    "expected_sha256": expected_sha256,
                    "filename": file_name,
                    "mime": mime_type,
                    "folder": folder,
                }
                final_result = await self._call_stream_action(bot, payload)

            complete_payload = {
                "stream_id": stream_id,
                "is_complete": True,
            }
            final_result = await self._call_stream_action(bot, complete_payload)
            uploaded_path = self._extract_uploaded_path(final_result)
            if uploaded_path:
                logger.info(f"NapCat Stream API uploaded file: {file_name} -> {uploaded_path}")
                return uploaded_path
            logger.warning(f"NapCat Stream API finished without a file path: {file_name}")
            return None
        except Exception as exc:
            logger.warning(f"NapCat Stream API upload failed: {file_name} - {exc}")
            return None

        logger.warning("NapCat Stream API unavailable on current OneBot client")
        return None

    async def upload_stream_then_send_file(
        self,
        event: Any,
        file_path: Path,
        *,
        name: str | None = None,
        folder: str = "/",
    ) -> bool:
        uploaded_path = await self.upload_file_stream(
            event,
            file_path,
            name=name,
            folder=folder,
        )
        if not uploaded_path:
            return False

        bot = getattr(event, "bot", None)
        if bot is None:
            return False
        file_name = name or Path(file_path).name
        try:
            group_id = event.get_group_id()
            if group_id:
                await self._call_onebot_action(
                    bot,
                    "upload_group_file",
                    group_id=int(group_id),
                    file=uploaded_path,
                    name=file_name,
                )
            else:
                await self._call_onebot_action(
                    bot,
                    "upload_private_file",
                    user_id=int(event.get_sender_id()),
                    file=uploaded_path,
                    name=file_name,
                )
            return True
        except Exception as exc:
            logger.warning(f"NapCat file send after stream upload failed: {file_name} - {exc}")
            return False

    async def upload_stream_then_send_video(
        self,
        event: Any,
        file_path: Path,
        *,
        name: str | None = None,
        folder: str = "/",
        allow_file_fallback: bool = True,
    ) -> bool:
        uploaded_path = await self.upload_file_stream(
            event,
            file_path,
            name=name,
            folder=folder,
        )
        if not uploaded_path:
            return False

        bot = getattr(event, "bot", None)
        if bot is None:
            return False

        file_name = name or Path(file_path).name
        try:
            message = [{"type": "video", "data": {"file": uploaded_path}}]
            await self._send_message(event, bot, message)
            logger.info(f"NapCat Stream video sent as video message: {file_name}")
            return True
        except Exception as exc:
            logger.warning(
                f"NapCat video message after stream upload failed, "
                f"trying file fallback: {file_name} - {exc}"
            )

        if not allow_file_fallback:
            return False

        try:
            await self._send_file(event, bot, uploaded_path, file_name)
            logger.info(f"NapCat Stream video sent as file fallback: {file_name}")
            return True
        except Exception as exc:
            logger.warning(f"NapCat file fallback after stream upload failed: {file_name} - {exc}")
            return False

    async def _call_stream_action(self, bot: Any, payload: dict[str, Any]) -> Any:
        return await self._call_onebot_action(bot, "upload_file_stream", **payload)

    async def _send_file(
        self,
        event: Any,
        bot: Any,
        uploaded_path: str,
        file_name: str,
    ) -> None:
        group_id = event.get_group_id()
        if group_id:
            await self._call_onebot_action(
                bot,
                "upload_group_file",
                group_id=int(group_id),
                file=uploaded_path,
                name=file_name,
            )
        else:
            await self._call_onebot_action(
                bot,
                "upload_private_file",
                user_id=int(event.get_sender_id()),
                file=uploaded_path,
                name=file_name,
            )

    async def _send_message(self, event: Any, bot: Any, message: list[dict[str, Any]]) -> None:
        group_id = event.get_group_id()
        if group_id:
            await self._call_onebot_action(
                bot,
                "send_group_msg",
                group_id=int(group_id),
                message=message,
            )
        else:
            await self._call_onebot_action(
                bot,
                "send_private_msg",
                user_id=int(event.get_sender_id()),
                message=message,
            )

    @staticmethod
    async def _call_onebot_action(bot: Any, action: str, **payload: Any) -> Any:
        direct = getattr(bot, action, None)
        if direct is not None:
            return await direct(**payload)

        for method_name in ("call_action", "call_api", "api"):
            caller = getattr(bot, method_name, None)
            if caller is None:
                continue
            return await caller(action, **payload)

        raise RuntimeError(f"current OneBot client has no action caller for {action}")

    @staticmethod
    def _extract_uploaded_path(result: Any) -> str | None:
        if isinstance(result, str):
            return result
        if not isinstance(result, dict):
            return None

        candidates = [result]
        data = result.get("data")
        if isinstance(data, dict):
            candidates.append(data)

        for item in candidates:
            for key in ("file", "path", "file_path", "url"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    return value
        return None
