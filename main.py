from __future__ import annotations

import base64
import re
import time
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.message.components import Image, Plain, Video

from .core.media_processor import MediaProcessor
from .core.napcat_stream_client import NapCatStreamClient
from .core.x_api_client import XApiClient
from .models.x_response_models import TweetResponse


TWEET_URL_PATTERN = re.compile(
    r"https?://(?:x|twitter)\.com/[A-Za-z0-9_]{1,15}/status/(\d+)",
    re.IGNORECASE,
)

DEFAULT_TWEET_TEXT_TEMPLATE = (
    "{author}\n\n"
    "{text}\n\n"
    "时间：{created_at}"
    "{metrics_line}"
    "{media_summary_line}\n"
    "链接：{url}"
)


@register(
    "astrbot_plugin_xparser",
    "seant",
    "Parse X/Twitter links and send tweet media through NapCat Stream API",
    "0.1.0",
)
class XParserPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.api_client = XApiClient(
            bearer_token=self._cfg("api_bearer_token", ""),
            api_key=self._cfg("api_key", ""),
            api_key_secret=self._cfg("api_key_secret", ""),
            oauth_access_token=self._cfg("oauth_access_token", ""),
            oauth_access_token_secret=self._cfg("oauth_access_token_secret", ""),
            cookie_auth_token=self._cfg("cookie_auth_token", ""),
            cookie_ct0=self._cfg("cookie_ct0", ""),
            graphql_tweet_query_id=self._cfg("graphql_tweet_query_id", ""),
            enable_proxy=bool(self._cfg("enable_proxy", True)),
            proxy_url=self._cfg("proxy_url", "http://127.0.0.1:7890"),
        )
        self.media_processor = MediaProcessor(
            forward_threshold_mb=int(self._cfg("download_limit_mb", 100)),
            pil_compress_target_kb=int(self._cfg("image_compress_target_kb", 2048)),
            image_compress_enabled=bool(self._cfg("enable_image_compression", True)),
            image_compress_mode=self._cfg("image_compress_mode", "target_size"),
            image_compress_quality=int(self._cfg("image_compress_quality", 85)),
            video_variant_strategy=self._cfg("video_variant_strategy", "highest"),
            display_media_details=True,
            enable_proxy=bool(self._cfg("enable_proxy", True)),
            proxy_url=self._cfg("proxy_url", "http://127.0.0.1:7890"),
        )
        self.stream_client = NapCatStreamClient(
            max_bytes=int(self._cfg("stream_max_mb", 100)) * 1024 * 1024
        )
        self.stream_threshold_bytes = int(self._cfg("stream_threshold_mb", 8)) * 1024 * 1024
        self.transfer_mode = self._normalize_transfer_mode(self._cfg("media_transfer_mode", "auto"))
        self.enable_auto_parse = bool(self._cfg("enable_auto_parse", True))
        self.tweet_text_template = str(
            self._cfg("tweet_text_template", DEFAULT_TWEET_TEXT_TEMPLATE)
            or DEFAULT_TWEET_TEXT_TEMPLATE
        )
        self.merge_text_and_images = bool(self._cfg("merge_text_and_images", True))
        self.max_merged_images = int(self._cfg("max_merged_images", 4))
        self.send_video_as_file = bool(self._cfg("send_video_as_file", True))
        self.cache_ttl_hours = int(self._cfg("cache_ttl_hours", 24))
        self.cache_dir: Path = StarTools.get_data_dir("astrbot_plugin_xparser")
        self.image_dir = self.cache_dir / "images"
        self.video_dir = self.cache_dir / "videos"
        for directory in (self.image_dir, self.video_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self._cleanup_cache()

    def _cfg(self, key: str, default: Any) -> Any:
        try:
            return self.config.get(key, default)
        except AttributeError:
            return default

    @filter.command("xparse")
    async def cmd_parse(self, event: AstrMessageEvent, url: str = ""):
        tweet_id = self._extract_tweet_id(url or event.message_str)
        if not tweet_id:
            await event.send(event.chain_result([Plain("请发送推文链接，例如 /xparse https://x.com/user/status/123")]))
            return
        await self._parse_and_send(event, tweet_id)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_parse_tweet_url(self, event: AstrMessageEvent):
        if not self.enable_auto_parse:
            return
        message_text = event.message_str or ""
        if message_text.lstrip().startswith("/xparse"):
            return
        tweet_id = self._extract_tweet_id(message_text)
        if not tweet_id:
            return
        await self._parse_and_send(event, tweet_id)

    async def _parse_and_send(self, event: AstrMessageEvent, tweet_id: str) -> None:
        try:
            response = await self.api_client.get_tweet(
                tweet_id=tweet_id,
                expansions="author_id,attachments.media_keys",
                tweet_fields="created_at,public_metrics,author_id",
                media_fields="url,variants,type,preview_image_url",
                user_fields="name,username,profile_image_url",
            )
            response = await self._process_tweet_media(response)
            text = self._format_tweet(response)
            await self._send_tweet(event, response, text)
        except Exception as exc:
            logger.error(f"XParser failed to parse tweet {tweet_id}: {exc}", exc_info=True)
            await event.send(event.chain_result([Plain(f"推文解析失败：{exc}")]))

    async def _process_tweet_media(self, response: TweetResponse) -> TweetResponse:
        if not response.includes or not response.includes.media:
            return response
        for media in response.includes.media:
            if media.variants:
                best = self.media_processor.select_best_variant(media.variants)
                if best and best.get("url"):
                    media.url = best["url"]
        return response

    def _format_tweet(self, response: TweetResponse) -> str:
        tweet = response.data
        author = response.includes.get_author_display(tweet.author_id) if response.includes else None
        if author:
            author_line = f"@{author['username']} ({author['name']})"
            author_name = author["name"]
            author_username = author["username"]
        else:
            author_line = f"tweet:{tweet.id}"
            author_name = ""
            author_username = ""

        like_count = retweet_count = reply_count = 0
        if tweet.public_metrics:
            like_count = tweet.public_metrics.like_count
            retweet_count = tweet.public_metrics.retweet_count
            reply_count = tweet.public_metrics.reply_count
        metrics_line = f"\n互动：点赞 {like_count} | 转发 {retweet_count} | 回复 {reply_count}"

        media_summary = self._media_summary(response).strip()
        media_summary_line = f"\n媒体：{media_summary}" if media_summary else ""
        url = f"https://x.com/i/status/{tweet.id}"
        values = {
            "author": author_line,
            "author_name": author_name,
            "author_username": author_username,
            "tweet_id": tweet.id,
            "text": tweet.text,
            "created_at": tweet.created_at or "",
            "like_count": like_count,
            "retweet_count": retweet_count,
            "reply_count": reply_count,
            "metrics_line": metrics_line,
            "media_summary": media_summary,
            "media_summary_line": media_summary_line,
            "url": url,
        }
        try:
            return self.tweet_text_template.format(**values).strip()
        except Exception as exc:
            logger.warning(f"推文输出模板渲染失败，已使用默认模板: {exc}")
            return DEFAULT_TWEET_TEXT_TEMPLATE.format(**values).strip()

    def _media_summary(self, response: TweetResponse) -> str:
        tweet = response.data
        if not tweet.attachments or not tweet.attachments.media_keys or not response.includes:
            return ""
        counts = {"photo": 0, "video": 0, "animated_gif": 0}
        for key in tweet.attachments.media_keys:
            media = response.includes.find_media_by_key(key)
            if media and media.type in counts:
                counts[media.type] += 1
        parts = []
        if counts["photo"]:
            parts.append(f"{counts['photo']} 张图片")
        if counts["video"]:
            parts.append(f"{counts['video']} 个视频")
        if counts["animated_gif"]:
            parts.append(f"{counts['animated_gif']} 个 GIF")
        return "，".join(parts) if parts else ""

    async def _send_tweet(
        self,
        event: AstrMessageEvent,
        response: TweetResponse,
        text: str,
    ) -> None:
        tweet = response.data
        if not tweet.attachments or not tweet.attachments.media_keys or not response.includes:
            await event.send(event.chain_result([Plain(text)]))
            return

        image_paths: list[Path] = []
        videos: list[tuple[Path, str]] = []

        for key in tweet.attachments.media_keys:
            media = response.includes.find_media_by_key(key)
            if not media:
                continue
            if media.type == "photo" and media.url:
                image_path = await self._download_image(tweet.id, media.url)
                if image_path:
                    image_paths.append(image_path)
            elif media.type in ("video", "animated_gif") and media.url:
                video_path = await self._download_video(tweet.id, media.url)
                if video_path:
                    videos.append((video_path, media.url))

        if not image_paths and not videos:
            await event.send(event.chain_result([Plain(text)]))
            return

        if image_paths:
            if self.merge_text_and_images:
                await self._send_text_with_images(event, text, image_paths)
            else:
                await event.send(event.chain_result([Plain(text)]))
                await self._send_images(event, image_paths)
        else:
            await event.send(event.chain_result([Plain(text)]))

        for video_path, source_url in videos:
            await self._send_video(event, video_path, source_url)

    async def _download_image(self, tweet_id: str, url: str) -> Path | None:
        try:
            data = await self.media_processor.download_media(url)
            if not data:
                return None
            data = await self.media_processor.compress_image(data)
            path = self.image_dir / f"img_{tweet_id}_{hash(url) & 0xFFFFFFFF}.jpg"
            path.write_bytes(data)
            return path
        except Exception as exc:
            logger.warning(f"Image media download failed: {url} - {exc}")
            return None

    async def _send_text_with_images(
        self,
        event: AstrMessageEvent,
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
        event: AstrMessageEvent,
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
        event: AstrMessageEvent,
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

    @staticmethod
    def _plain_segment(text: str) -> dict[str, Any]:
        return {"type": "text", "data": {"text": text}}

    @staticmethod
    def _image_segment(path: Path) -> dict[str, Any]:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {"type": "image", "data": {"file": f"base64://{encoded}"}}

    async def _download_video(self, tweet_id: str, url: str) -> Path | None:
        try:
            data = await self.media_processor.download_media(url)
            if not data:
                return None
            path = self.video_dir / f"vid_{tweet_id}_{hash(url) & 0xFFFFFFFF}.mp4"
            path.write_bytes(data)
            return path
        except Exception as exc:
            logger.warning(f"Video media download failed: {url} - {exc}")
            return None

    async def _send_video(self, event: AstrMessageEvent, path: Path, source_url: str) -> None:
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
    def _extract_tweet_id(text: str) -> str | None:
        match = TWEET_URL_PATTERN.search(text or "")
        return match.group(1) if match else None

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

    @staticmethod
    def _normalize_transfer_mode(value: Any) -> str:
        mode = str(value or "auto").strip().lower()
        if mode in {"auto", "stream", "local"}:
            return mode
        logger.warning(f"未知媒体传输模式 {value!r}，已回退为 auto")
        return "auto"

    def _cleanup_cache(self) -> None:
        if self.cache_ttl_hours <= 0:
            return
        cutoff = time.time() - self.cache_ttl_hours * 3600
        for directory in (self.image_dir, self.video_dir):
            for item in directory.glob("*"):
                try:
                    if item.is_file() and item.stat().st_mtime < cutoff:
                        item.unlink()
                except Exception as exc:
                    logger.debug(f"Cache cleanup skipped {item}: {exc}")

    async def terminate(self):
        if hasattr(self.api_client, "close"):
            await self.api_client.close()
        if hasattr(self.media_processor, "close"):
            await self.media_processor.close()
