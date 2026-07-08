from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.message.components import Plain

from .adapters.onebot_napcat import OneBotNapCatSender
from .core.access_control import (
    AccessControl,
    AccessControlConfig,
    normalize_acl_mode,
    normalize_id_set,
)
from .core.media_processor import MediaProcessor
from .core.napcat_stream_client import NapCatStreamClient
from .core.temp_media_registry import TempMediaRegistry
from .core.temp_media_server import TempMediaServer
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
        self._maybe_migrate_temp_media_base_url_config()
        self.api_client = XApiClient(
            bearer_token=self._cfg("auth.api_bearer_token", "", "api_bearer_token"),
            api_key=self._cfg("auth.api_key", "", "api_key"),
            api_key_secret=self._cfg("auth.api_key_secret", "", "api_key_secret"),
            oauth_access_token=self._cfg(
                "auth.oauth_access_token", "", "oauth_access_token"
            ),
            oauth_access_token_secret=self._cfg(
                "auth.oauth_access_token_secret", "", "oauth_access_token_secret"
            ),
            cookie_auth_token=self._cfg(
                "auth.cookie_auth_token", "", "cookie_auth_token"
            ),
            cookie_ct0=self._cfg("auth.cookie_ct0", "", "cookie_ct0"),
            graphql_tweet_query_id=self._cfg(
                "auth.graphql_tweet_query_id", "", "graphql_tweet_query_id"
            ),
            enable_proxy=bool(self._cfg("network.enable_proxy", True, "enable_proxy")),
            proxy_url=self._cfg(
                "network.proxy_url",
                "http://127.0.0.1:7890",
                "proxy_url",
            ),
        )
        self.media_processor = MediaProcessor(
            forward_threshold_mb=int(
                self._cfg("media.download_limit_mb", 100, "download_limit_mb")
            ),
            pil_compress_target_kb=int(
                self._cfg(
                    "media.image_compress_target_kb",
                    2048,
                    "image_compress_target_kb",
                )
            ),
            image_compress_enabled=bool(
                self._cfg(
                    "media.enable_image_compression",
                    True,
                    "enable_image_compression",
                )
            ),
            image_compress_mode=self._cfg(
                "media.image_compress_mode",
                "target_size",
                "image_compress_mode",
            ),
            image_compress_quality=int(
                self._cfg("media.image_compress_quality", 85, "image_compress_quality")
            ),
            video_variant_strategy=self._cfg(
                "media.video_variant_strategy",
                "highest",
                "video_variant_strategy",
            ),
            display_media_details=True,
            enable_proxy=bool(self._cfg("network.enable_proxy", True, "enable_proxy")),
            proxy_url=self._cfg(
                "network.proxy_url",
                "http://127.0.0.1:7890",
                "proxy_url",
            ),
        )
        self.stream_client = NapCatStreamClient(
            max_bytes=int(self._cfg("send.stream_max_mb", 100, "stream_max_mb"))
            * 1024
            * 1024
        )
        temp_media_http_port = int(
            self._cfg(
                "send.temp_media_http_port",
                6190,
                "temp_media_http_port",
            )
        )
        temp_media_base_url = self._normalize_temp_media_base_url(
            str(
                self._cfg(
                    "send.temp_media_base_url",
                    "http://astrbot",
                    "temp_media_base_url",
                )
                or "http://astrbot"
            ),
            temp_media_http_port,
        )
        self.temp_media_registry = TempMediaRegistry()
        self.temp_media_server = TempMediaServer(
            self.temp_media_registry,
            base_url=temp_media_base_url,
            path_prefix=str(
                self._cfg(
                    "send.temp_media_path_prefix",
                    "/xparser/media",
                    "temp_media_path_prefix",
                )
                or "/xparser/media"
            ),
            host=str(
                self._cfg(
                    "send.temp_media_http_host",
                    "0.0.0.0",
                    "temp_media_http_host",
                )
                or "0.0.0.0"
            ),
            port=temp_media_http_port,
            enabled=bool(
                self._cfg(
                    "send.enable_temp_media_http_server",
                    True,
                    "enable_temp_media_http_server",
                )
                and self._cfg(
                    "send.enable_temp_media_http_fallback",
                    True,
                    "enable_temp_media_http_fallback",
                )
            ),
        )
        self.stream_threshold_bytes = (
            int(self._cfg("send.stream_threshold_mb", 8, "stream_threshold_mb"))
            * 1024
            * 1024
        )
        transfer_mode = self._normalize_transfer_mode(
            self._cfg("send.media_transfer_mode", "auto", "media_transfer_mode")
        )
        self.enable_auto_parse = bool(
            self._cfg("parse.enable_auto_parse", True, "enable_auto_parse")
        )
        self.tweet_text_template = str(
            self._cfg(
                "parse.tweet_text_template",
                DEFAULT_TWEET_TEXT_TEMPLATE,
                "tweet_text_template",
            )
            or DEFAULT_TWEET_TEXT_TEMPLATE
        )
        self.access_control = AccessControl(
            AccessControlConfig(
                cooldown_seconds=max(
                    0, int(self._cfg("access.cooldown_seconds", 10, "cooldown_seconds"))
                ),
                same_tweet_cooldown_seconds=max(
                    0,
                    int(
                        self._cfg(
                            "access.same_tweet_cooldown_seconds",
                            120,
                            "same_tweet_cooldown_seconds",
                        )
                    ),
                ),
                acl_mode=normalize_acl_mode(
                    self._cfg("access.acl_mode", "关闭", "acl_mode")
                ),
                allowed_group_ids=normalize_id_set(
                    self._cfg("access.allowed_group_ids", [], "allowed_group_ids")
                ),
                allowed_private_user_ids=normalize_id_set(
                    self._cfg(
                        "access.allowed_private_user_ids",
                        [],
                        "allowed_private_user_ids",
                    )
                ),
                blocked_group_ids=normalize_id_set(
                    self._cfg("access.blocked_group_ids", [], "blocked_group_ids")
                ),
                blocked_private_user_ids=normalize_id_set(
                    self._cfg(
                        "access.blocked_private_user_ids",
                        [],
                        "blocked_private_user_ids",
                    )
                ),
            )
        )
        self.sender = OneBotNapCatSender(
            self.stream_client,
            transfer_mode=transfer_mode,
            stream_threshold_bytes=self.stream_threshold_bytes,
            send_mode=self._normalize_send_mode(
                self._cfg("send.send_mode", "普通消息", "send_mode")
            ),
            forward_node_name=str(
                self._cfg("send.forward_node_name", "X 推文解析", "forward_node_name")
                or "X 推文解析"
            ),
            merge_text_and_images=bool(
                self._cfg("send.merge_text_and_images", True, "merge_text_and_images")
            ),
            max_merged_images=int(
                self._cfg("send.max_merged_images", 4, "max_merged_images")
            ),
            send_video_as_file=bool(
                self._cfg("send.send_video_as_file", True, "send_video_as_file")
            ),
            temp_media_server=self.temp_media_server,
            temp_media_ttl_seconds=int(
                self._cfg(
                    "send.temp_media_ttl_seconds",
                    300,
                    "temp_media_ttl_seconds",
                )
            ),
        )
        self.cache_ttl_hours = int(
            self._cfg("media.cache_ttl_hours", 24, "cache_ttl_hours")
        )
        self.cache_dir: Path = StarTools.get_data_dir("astrbot_plugin_xparser")
        self.image_dir = self.cache_dir / "images"
        self.video_dir = self.cache_dir / "videos"
        for directory in (self.image_dir, self.video_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self._cleanup_cache()

    async def initialize(self):
        try:
            await self.temp_media_server.setup()
        except Exception as exc:
            logger.warning(
                "Temp media HTTP server failed to start on "
                f"{self.temp_media_server.host}:{self.temp_media_server.port}: {exc}. "
                "Please change send.temp_media_http_port and send.temp_media_base_url."
            )
        self.temp_media_registry.cleanup_expired()

    def _cfg(self, key: str, default: Any, legacy_key: str | None = None) -> Any:
        missing = object()
        try:
            current: Any = self.config
            for part in key.split("."):
                if not hasattr(current, "get"):
                    current = missing
                    break
                current = current.get(part, missing)
                if current is missing:
                    break
            if current is not missing:
                return current
            if legacy_key:
                return self.config.get(legacy_key, default)
            return default
        except AttributeError:
            return default

    def _set_cfg(self, key: str, value: Any, legacy_key: str | None = None) -> bool:
        try:
            current: Any = self.config
            parts = key.split(".")
            for part in parts[:-1]:
                child = None
                getter = getattr(current, "get", None)
                if getter is not None:
                    child = getter(part, None)
                elif isinstance(current, dict):
                    child = current.get(part)
                if child is None:
                    if isinstance(current, dict):
                        current[part] = {}
                        child = current[part]
                    else:
                        return False
                current = child

            last = parts[-1]
            setter = getattr(current, "set", None)
            if setter is not None:
                setter(last, value)
                return True
            if isinstance(current, dict):
                current[last] = value
                return True
            if hasattr(current, "__setitem__"):
                current[last] = value
                return True

            if legacy_key:
                root_setter = getattr(self.config, "set", None)
                if root_setter is not None:
                    root_setter(legacy_key, value)
                    return True
                if isinstance(self.config, dict):
                    self.config[legacy_key] = value
                    return True
            return False
        except Exception as exc:
            logger.debug(f"Temp media config migration skipped: {exc}")
            return False

    def _maybe_migrate_temp_media_base_url_config(self) -> None:
        current_value = str(
            self._cfg(
                "send.temp_media_base_url",
                "",
                "temp_media_base_url",
            )
            or ""
        ).strip()
        if current_value not in {"http://astrbot:6185", "http://astrbot:6190"}:
            return
        if self._set_cfg(
            "send.temp_media_base_url",
            "http://astrbot",
            legacy_key="temp_media_base_url",
        ):
            logger.info(
                "Migrated temp_media_base_url from legacy fixed-port value to http://astrbot"
            )

    @staticmethod
    def _normalize_temp_media_base_url(base_url: str, port: int) -> str:
        value = (base_url or "").strip().rstrip("/")
        if not value:
            value = "http://astrbot"

        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            return value
        if parsed.port is not None:
            return value

        host = parsed.hostname or parsed.netloc
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        netloc = host
        if parsed.username:
            userinfo = parsed.username
            if parsed.password:
                userinfo += f":{parsed.password}"
            netloc = f"{userinfo}@{netloc}"
        netloc = f"{netloc}:{port}"
        return urlunparse(parsed._replace(netloc=netloc)).rstrip("/")

    @filter.command("xparse")
    async def cmd_parse(self, event: AstrMessageEvent, url: str = ""):
        tweet_id = self._extract_tweet_id(url or event.message_str)
        if not tweet_id:
            await event.send(
                event.chain_result(
                    [Plain("请发送推文链接，例如 /xparse https://x.com/user/status/123")]
                )
            )
            return
        if not await self._can_parse_event(event, tweet_id, silent=False):
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
        if not await self._can_parse_event(event, tweet_id, silent=True):
            return
        await self._parse_and_send(event, tweet_id)

    async def _can_parse_event(
        self,
        event: AstrMessageEvent,
        tweet_id: str,
        *,
        silent: bool,
    ) -> bool:
        allowed, reason = self.access_control.check(event, tweet_id)
        if not allowed and not silent and reason:
            await event.send(event.chain_result([Plain(reason)]))
        return allowed

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
        author = (
            response.includes.get_author_display(tweet.author_id)
            if response.includes
            else None
        )
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

        image_items: list[tuple[Path, str]] = []
        videos: list[tuple[Path, str]] = []

        for key in tweet.attachments.media_keys:
            media = response.includes.find_media_by_key(key)
            if not media:
                continue
            if media.type == "photo" and media.url:
                image_path = await self._download_image(tweet.id, media.url)
                if image_path:
                    image_items.append((image_path, media.url))
            elif media.type in ("video", "animated_gif") and media.url:
                video_path = await self._download_video(tweet.id, media.url)
                if video_path:
                    videos.append((video_path, media.url))

        if not image_items and not videos:
            await event.send(event.chain_result([Plain(text)]))
            return

        await self.sender.send_tweet_media(event, text, image_items, videos)

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

    @staticmethod
    def _extract_tweet_id(text: str) -> str | None:
        match = TWEET_URL_PATTERN.search(text or "")
        return match.group(1) if match else None

    @staticmethod
    def _normalize_transfer_mode(value: Any) -> str:
        mode = str(value or "auto").strip().lower()
        if mode in {"auto", "stream", "local"}:
            return mode
        logger.warning(f"未知媒体传输模式 {value!r}，已回退为 auto")
        return "auto"

    @staticmethod
    def _normalize_send_mode(value: Any) -> str:
        mode = str(value).strip().lower()
        aliases = {
            "普通消息": "normal",
            "普通发送": "normal",
            "合并转发": "forward",
            "plain": "normal",
            "forward": "forward",
            "normal": "normal",
        }
        normalized = aliases.get(mode, mode)
        if normalized in {"normal", "forward"}:
            return normalized
        logger.warning(f"未知发送模式 {value!r}，已回退为普通消息")
        return "normal"

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
        if hasattr(self.temp_media_server, "close"):
            await self.temp_media_server.close()
        if hasattr(self.api_client, "close"):
            await self.api_client.close()
        if hasattr(self.media_processor, "close"):
            await self.media_processor.close()
