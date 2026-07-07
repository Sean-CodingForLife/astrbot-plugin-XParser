from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.core.message.components import Image, Plain, Video

from ..core.napcat_stream_client import NapCatStreamClient


class OneBotNapCatSender:
    def __init__(
        self,
        stream_client: NapCatStreamClient,
        *,
        transfer_mode: str,
        stream_threshold_bytes: int,
        send_mode: str,
        merge_text_and_images: bool,
        max_merged_images: int,
        send_video_as_file: bool,
    ):
        self.stream_client = stream_client
        self.transfer_mode = transfer_mode
        self.stream_threshold_bytes = stream_threshold_bytes
        self.send_mode = send_mode
        self.merge_text_and_images = merge_text_and_images
        self.max_merged_images = max_merged_images
        self.send_video_as_file = send_video_as_file

    async def send_tweet_media(
        self,
        event: Any,
        text: str,
        image_paths: list[Path],
        videos: list[tuple[Path, str]],
    ) -> None:
        if not image_paths and not videos:
            await event.send(event.chain_result([Plain(text)]))
            return

        if self.send_mode == "forward" and (image_paths or videos):
            if await self._send_forward_message(event, text, image_paths, len(videos)):
                pass
            else:
                logger.warning("Forward message send failed or unsupported, falling back to normal message mode")
                await self._send_ordinary_tweet_message(
                    event,
                    text,
                    image_paths,
                    prefer_merged=self.merge_text_and_images,
                )
        else:
            await self._send_ordinary_tweet_message(
                event,
                text,
                image_paths,
                prefer_merged=self.merge_text_and_images,
            )

        for video_path, source_url in videos:
            await self._send_video(event, video_path, source_url)

    async def _send_ordinary_tweet_message(
        self,
        event: Any,
        text: str,
        image_paths: list[Path],
        *,
        prefer_merged: bool,
    ) -> None:
        if image_paths:
            if prefer_merged:
                await self._send_text_with_images(event, text, image_paths)
            else:
                await event.send(event.chain_result([Plain(text)]))
                await self._send_images(event, image_paths)
            return

        await event.send(event.chain_result([Plain(text)]))

    async def _send_forward_message(
        self,
        event: Any,
        text: str,
        image_paths: list[Path],
        video_count: int,
    ) -> bool:
        if not NapCatStreamClient.is_aiocqhttp_event(event):
            return False

        nodes: list[dict[str, Any]] = [self._forward_node([self._plain_segment(text)])]
        for index, path in enumerate(image_paths, start=1):
            nodes.append(
                self._forward_node(
                    [
                        self._plain_segment(f"图片 {index}/{len(image_paths)}"),
                        self._image_segment(path),
                    ]
                )
            )

        if video_count:
            nodes.append(
                self._forward_node(
                    [
                        self._plain_segment(
                            f"视频/GIF 共 {video_count} 个，将在合并转发消息后单独发送。"
                        )
                    ]
                )
            )

        try:
            await self._send_onebot_forward(event, nodes)
            return True
        except Exception as exc:
            logger.warning(f"OneBot forward message send failed: {exc}")
            return False

    async def _send_text_with_images(
        self,
        event: Any,
        text: str,
        image_paths: list[Path],
    ) -> None:
        if not image_paths:
            await event.send(event.chain_result([Plain(text)]))
            return

        merge_count = max(0, min(self.max_merged_images, len(image_paths)))
        merged_paths = image_paths[:merge_count]
        remaining_paths = image_paths[merge_count:]

        if NapCatStreamClient.is_aiocqhttp_event(event):
            await self._send_onebot_message(
                event,
                [self._plain_segment(text), *[self._image_segment(path) for path in merged_paths]],
            )
        else:
            components = [Plain(text), *[Image.fromFileSystem(str(path)) for path in merged_paths]]
            await event.send(event.chain_result(components))

        if remaining_paths:
            await self._send_images(event, remaining_paths)

    async def _send_images(
        self,
        event: Any,
        image_paths: list[Path],
    ) -> None:
        if NapCatStreamClient.is_aiocqhttp_event(event):
            for path in image_paths:
                try:
                    await self._send_onebot_message(event, [self._image_segment(path)])
                except Exception as exc:
                    logger.warning(f"OneBot base64 image send failed: {path} - {exc}")
                    await event.send(event.chain_result([Plain(f"图片发送失败：{path.name}")]))
            return

        image_components = [Image.fromFileSystem(str(path)) for path in image_paths]
        await event.send(event.chain_result(image_components))

    async def _send_onebot_message(
        self,
        event: Any,
        message: list[dict[str, Any]],
    ) -> None:
        bot = getattr(event, "bot", None)
        if bot is None:
            await event.send(
                event.chain_result([Plain("消息发送失败：当前 aiocqhttp 事件没有可用的 bot 客户端。")])
            )
            return

        group_id = event.get_group_id()
        user_id = event.get_sender_id()
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
                user_id=int(user_id),
                message=message,
            )

    async def _send_onebot_forward(
        self,
        event: Any,
        messages: list[dict[str, Any]],
    ) -> None:
        bot = getattr(event, "bot", None)
        if bot is None:
            raise RuntimeError("当前 aiocqhttp 事件没有可用的 bot 客户端")

        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        if group_id:
            await self._call_onebot_action(
                bot,
                "send_group_forward_msg",
                group_id=int(group_id),
                messages=messages,
            )
        else:
            await self._call_onebot_action(
                bot,
                "send_private_forward_msg",
                user_id=int(user_id),
                messages=messages,
            )

    def _forward_node(self, content: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "type": "node",
            "data": {
                "name": "XParser",
                "uin": "10000",
                "content": content,
            },
        }

    async def _send_video(self, event: Any, path: Path, source_url: str) -> None:
        use_stream = self.transfer_mode == "stream" or (
            self.transfer_mode == "auto" and path.stat().st_size >= self.stream_threshold_bytes
        )

        if use_stream or self.transfer_mode == "stream":
            if await self.stream_client.upload_stream_then_send_video(
                event,
                path,
                allow_file_fallback=self.send_video_as_file,
            ):
                return
            if self.transfer_mode == "stream":
                await event.send(event.chain_result([Plain(f"Stream API 上传失败，原始直链：{source_url}")]))
                return

        try:
            if self.transfer_mode in ("auto", "local"):
                await event.send(event.chain_result([Video.fromFileSystem(str(path))]))
                return
        except Exception as exc:
            logger.warning(f"Video component send failed, trying stream fallback: {source_url} - {exc}")

        if await self.stream_client.upload_stream_then_send_video(
            event,
            path,
            allow_file_fallback=self.send_video_as_file,
        ):
            return

        await event.send(event.chain_result([Plain(f"视频发送失败，原始直链：{source_url}")]))

    @staticmethod
    def _plain_segment(text: str) -> dict[str, Any]:
        return {"type": "text", "data": {"text": text}}

    @staticmethod
    def _image_segment(path: Path) -> dict[str, Any]:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {"type": "image", "data": {"file": f"base64://{encoded}"}}

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

        raise RuntimeError(f"当前 OneBot 客户端不支持动作 {action}")
