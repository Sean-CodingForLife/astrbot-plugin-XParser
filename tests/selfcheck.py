r"""插件离线自检脚本。

用途：在没有安装 AstrBot 的环境下，通过桩模块导入插件本体，
验证解析、媒体处理、发送链路与 API 错误分类等关键行为。

运行方式（在插件根目录执行）：

    python tests/selfcheck.py

脚本会自动把插件复制到 `tests/_stage/xparser_plugin`，
以便用 `import xparser_plugin.xxx` 触发真实的相对导入，
运行结束后会清理该目录。退出码 0 表示全部通过。
"""

from __future__ import annotations

import asyncio
import atexit
import shutil
import sys
import types
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
TMP_ROOT = TESTS_DIR / "_stage"

PLUGIN_PKG = "xparser_plugin"
PLUGIN_SRC = TMP_ROOT / PLUGIN_PKG

# 需要复制的插件文件（目录形式），tests/ 自身不参与复制
_PLUGIN_FILES = ("main.py", "metadata.yaml", "_conf_schema.json", "requirements.txt")
_PLUGIN_DIRS = ("adapters", "core", "models")


def _stage_plugin() -> None:
    if TMP_ROOT.exists():
        shutil.rmtree(TMP_ROOT, ignore_errors=True)
    PLUGIN_SRC.mkdir(parents=True, exist_ok=True)
    for name in _PLUGIN_FILES:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, PLUGIN_SRC / name)
    for name in _PLUGIN_DIRS:
        source_dir = ROOT / name
        if not source_dir.is_dir():
            continue
        target_dir = PLUGIN_SRC / name
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in source_dir.glob("*.py"):
            shutil.copy2(item, target_dir / item.name)


_stage_plugin()
atexit.register(lambda: shutil.rmtree(TMP_ROOT, ignore_errors=True))
sys.path.insert(0, str(TMP_ROOT))

if not (PLUGIN_SRC / "main.py").exists():
    raise SystemExit(f"插件暂存失败，未找到 {PLUGIN_SRC / 'main.py'}")


# ---------------------------------------------------------------- AstrBot 桩
def _module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


class _Logger:
    def __getattr__(self, item):
        def _log(*args, **kwargs):
            print(f"[{item}]", *args)

        return _log


class Plain:
    def __init__(self, text: str = ""):
        self.text = text


class Image:
    @staticmethod
    def fromFileSystem(path: str):
        return f"image:{path}"


class Video:
    @staticmethod
    def fromFileSystem(path: str):
        return f"video:{path}"


class MessageEventResult:
    def __init__(self, chain=None):
        self.chain = chain


class AstrMessageEvent:
    pass


class _Filter:
    class EventMessageType:
        ALL = "ALL"

    @staticmethod
    def command(name):
        def deco(fn):
            return fn

        return deco

    @staticmethod
    def event_message_type(kind):
        def deco(fn):
            return fn

        return deco


def register(name, author, desc, version, repo=None):
    def deco(cls):
        cls.__plugin_meta__ = (name, author, desc, version, repo)
        return cls

    return deco


class Star:
    def __init__(self, context=None):
        self.context = context


class StarTools:
    @staticmethod
    def get_data_dir(name=None):
        d = TMP_ROOT / "_tmp_data" / (name or "unknown")
        d.mkdir(parents=True, exist_ok=True)
        return d


class Context:
    pass


class AstrBotConfig(dict):
    pass


setattr(_module("astrbot"), "logger", _Logger())
setattr(sys.modules["astrbot"], "AstrBotConfig", AstrBotConfig)

api = _module("astrbot.api")
api.logger = sys.modules["astrbot"].logger
api.AstrBotConfig = AstrBotConfig

event_mod = _module("astrbot.api.event")
event_mod.AstrMessageEvent = AstrMessageEvent
event_mod.filter = _Filter

star_mod = _module("astrbot.api.star")
star_mod.Context = Context
star_mod.Star = Star
star_mod.StarTools = StarTools
star_mod.register = register
star_mod.star_map = {}

_module("astrbot.core")
components = _module("astrbot.core.message.components")
components.Plain = Plain
components.Image = Image
components.Video = Video
components.BaseMessageComponent = object
message_event_result = _module("astrbot.core.message.message_event_result")
message_event_result.MessageChain = list
message_event_result.MessageEventResult = MessageEventResult

# ------------------------------------------------- 第三方依赖桩（本地环境未安装）
httpx = _module("httpx")


class _HttpError(Exception):
    pass


class _TimeoutException(_HttpError):
    pass


class _ConnectError(_HttpError):
    pass


class _Timeout:
    def __init__(self, *args, **kwargs):
        pass


class _Response:
    status_code = 200
    text = "{}"
    headers: dict = {}

    def json(self):
        return {}


class _AsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def aclose(self):
        pass

    async def request(self, *args, **kwargs):
        return _Response()

    async def head(self, *args, **kwargs):
        return _Response()

    def stream(self, *args, **kwargs):
        raise NotImplementedError


httpx.TimeoutException = _TimeoutException
httpx.ConnectError = _ConnectError
httpx.Timeout = _Timeout
httpx.AsyncClient = _AsyncClient

pil = _module("PIL")


class _PILImage:
    class Resampling:
        LANCZOS = "LANCZOS"

    @staticmethod
    def open(*args, **kwargs):
        raise NotImplementedError

    @staticmethod
    def new(*args, **kwargs):
        raise NotImplementedError


pil.Image = _PILImage

aiohttp = _module("aiohttp")


class _HTTPException(Exception):
    def __init__(self, **kwargs):
        super().__init__(kwargs.get("text", ""))


class _Router:
    def add_get(self, *args, **kwargs):
        pass


class _Application:
    def __init__(self):
        self.router = _Router()


class _Response:
    def __init__(self, *args, **kwargs):
        self.headers: dict = {}


class _AppRunner:
    def __init__(self, app):
        self.app = app

    async def setup(self):
        pass

    async def cleanup(self):
        pass


class _TCPSite:
    def __init__(self, runner, host, port):
        self.runner = runner
        self.host = host
        self.port = port

    async def start(self):
        pass

    async def stop(self):
        pass


class _Web:
    Application = _Application
    AppRunner = _AppRunner
    TCPSite = _TCPSite
    StreamResponse = _Response
    FileResponse = _Response
    Request = object
    HTTPNotFound = _HTTPException


aiohttp.web = _Web
_module("aiohttp.web").__dict__.update(_Web.__dict__)

# ---------------------------------------------------------------- 导入插件
import importlib

importlib.import_module(PLUGIN_PKG)
main_mod = importlib.import_module(f"{PLUGIN_PKG}.main")

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    if not condition:
        failures.append(f"{label} :: {detail}")
    print(f"[{status}] {label} {detail}")


XParserPlugin = main_mod.XParserPlugin

print("== register 元数据顺序 ==")
name, author, desc, version, repo = XParserPlugin.__plugin_meta__
check("register author 位置", author == "seant", f"author={author!r}")
check("register version 位置", version == "0.1.1", f"version={version!r}")
check("register desc 位置", "X/Twitter" in desc, f"desc={desc[:20]!r}")

print("\n== temp_media_base_url 归一化 ==")
norm = XParserPlugin._normalize_temp_media_base_url
check("无端口自动拼接", norm("http://astrbot", 6190) == "http://astrbot:6190", norm("http://astrbot", 6190))
check("显式端口保留", norm("http://astrbot:8080", 6190) == "http://astrbot:8080")
check("非法端口不抛异常且改用配置端口", norm("http://astrbot:abc", 6190) == "http://astrbot:6190", norm("http://astrbot:abc", 6190))
check("空值回退默认", norm("", 6190) == "http://astrbot:6190", norm("", 6190))
check("IPv6 保留方括号", norm("http://[::1]", 6190) == "http://[::1]:6190", norm("http://[::1]", 6190))
check("带路径保留", norm("http://astrbot/base", 6190) == "http://astrbot:6190/base", norm("http://astrbot/base", 6190))

print("\n== 图片格式嗅探 ==")
from xparser_plugin.core.media_utils import guess_image_extension, image_mime_for_path

check("JPEG 头", guess_image_extension(b"\xff\xd8\xff\xe0abc") == ".jpg")
check("PNG 头", guess_image_extension(b"\x89PNG\r\n\x1a\nabc") == ".png")
check("GIF 头", guess_image_extension(b"GIF89a....") == ".gif")
check("WebP 头", guess_image_extension(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ".webp")
check("未知回退", guess_image_extension(b"\x00\x01\x02", ".jpg") == ".jpg")
check("MIME 推断", image_mime_for_path(Path("a.png")) == "image/png")

print("\n== 推文链接提取 ==")
check("x.com", XParserPlugin._extract_tweet_id("看这个 https://x.com/a/status/1234567890 好") == "1234567890")
check("twitter.com", XParserPlugin._extract_tweet_id("https://twitter.com/a/status/42") == "42")
check("非推文链接", XParserPlugin._extract_tweet_id("https://x.com/a") is None)


print("\n== 端到端：图片扩展名 + 发送链路 ==")


class FakeAccessControl:
    def check(self, event, tweet_id):
        return True, None


class SimpleTweet:
    id = "1234567890"
    author_id = "u1"
    text = "hello"
    created_at = None
    public_metrics = None
    attachments = None


class SimpleIncludes:
    def __init__(self, media):
        self.media = media

    def get_author_display(self, _):
        return {"name": "N", "username": "u"}

    def find_media_by_key(self, key):
        for m in self.media:
            if m.media_key == key:
                return m
        return None


class FakeMedia:
    def __init__(self, mtype, url, variants=None, key="k1"):
        self.type = mtype
        self.url = url
        self.variants = variants
        self.media_key = key


class FakeAttachments:
    def __init__(self, keys):
        self.media_keys = keys


class FakeResponse:
    def __init__(self, media=None):
        self.data = SimpleTweet()
        self.includes = SimpleIncludes(media or [])


class FakeProcessor:
    def __init__(self):
        self.selected = []

    def select_best_variant(self, variants):
        self.selected.append([v.content_type for v in variants])
        return {
            "url": "https://video.twimg.com/best.mp4",
            "bit_rate": 1,
            "content_type": "video/mp4",
        }

    async def download_media(self, url):
        if url.endswith(".png"):
            return b"\x89PNG\r\n\x1a\n" + b"0" * 64
        return b"\xff\xd8\xff" + b"0" * 64

    async def compress_image(self, data):
        return data


async def e2e():
    plugin = XParserPlugin.__new__(XParserPlugin)
    plugin.media_processor = FakeProcessor()
    plugin.image_dir = TMP_ROOT / "_tmp_data" / "images"
    plugin.video_dir = TMP_ROOT / "_tmp_data" / "videos"
    plugin.image_dir.mkdir(parents=True, exist_ok=True)
    plugin.video_dir.mkdir(parents=True, exist_ok=True)
    plugin.access_control = FakeAccessControl()
    plugin.enable_auto_parse = True

    png_path = await plugin._download_image("123", "https://pbs.twimg.com/media/a.png")
    check("PNG 落盘扩展名", png_path is not None and png_path.suffix == ".png", str(png_path))
    jpg_path = await plugin._download_image("123", "https://pbs.twimg.com/media/b.jpg")
    check("JPEG 落盘扩展名", jpg_path is not None and jpg_path.suffix == ".jpg", str(jpg_path))
    check(
        "文件名摘要稳定",
        XParserPlugin._url_digest("https://x/a") == XParserPlugin._url_digest("https://x/a"),
    )

    from xparser_plugin.models.x_response_models import MediaVariant

    photo = FakeMedia("photo", "https://pbs.twimg.com/media/p.jpg", None, "p")
    video = FakeMedia(
        "video",
        "https://video.twimg.com/src.mp4",
        [MediaVariant(content_type="video/mp4", url="https://video.twimg.com/best.mp4", bit_rate=100)],
        "v",
    )
    resp = FakeResponse(media=[photo, video])
    await plugin._process_tweet_media(resp)
    check("图片 URL 未被变体覆盖", photo.url == "https://pbs.twimg.com/media/p.jpg", photo.url)
    check("视频 URL 已替换为最佳变体", video.url == "https://video.twimg.com/best.mp4", video.url)

    stopped = {"value": False}
    sent = []

    class FakeEvent:
        message_str = "看看 https://x.com/a/status/1234567890"

        def stop_event(self):
            stopped["value"] = True

        async def send(self, result):
            sent.append(result)

        def chain_result(self, chain):
            return chain

    class FakeSender:
        async def send_tweet_media(self, event, text, images, videos):
            sent.append(("media", text, len(images), len(videos)))

    plugin.sender = FakeSender()
    plugin.api_client = types.SimpleNamespace()

    async def fake_get_tweet(**kwargs):
        tweet = SimpleTweet()
        tweet.attachments = FakeAttachments(["p"])
        return FakeResponse(media=[photo])

    plugin.api_client.get_tweet = fake_get_tweet
    await plugin.auto_parse_tweet_url(FakeEvent())
    check("自动解析后 stop_event", stopped["value"] is True)
    check("自动解析已投递", len(sent) == 1, str(sent))

    class DeniedAccess:
        def check(self, event, tweet_id):
            return False, "冷却中"

    plugin.access_control = DeniedAccess()
    stopped["value"] = False
    sent.clear()
    await plugin.auto_parse_tweet_url(FakeEvent())
    check("冷却命中不发送", not sent)
    check("冷却命中不终止事件", stopped["value"] is False)


asyncio.run(e2e())

print("\n== 视频投递模式 ==")
from xparser_plugin.adapters.onebot_sender import OneBotSender


class FakeStreamClient:
    def __init__(self):
        self.calls = 0
        self.status = "skipped"

    async def upload_stream_then_send_video_status(self, event, path, *, allow_file_fallback=True):
        self.calls += 1
        return self.status


class FakeVideoEvent:
    def __init__(self):
        self.sent = []

    def get_platform_name(self):
        # 非 aiocqhttp：跳过 URL 直发轮次，专门验证本地/流式决策
        return "other"

    async def send(self, result):
        self.sent.append(result)

    def chain_result(self, chain):
        return chain


def make_sender(client, transfer_mode):
    return OneBotSender(
        client,
        transfer_mode=transfer_mode,
        stream_threshold_bytes=1,
        send_mode="normal",
        forward_node_name="n",
        forward_node_uin_mode="bot",
        forward_node_uin="10000",
        merge_text_and_images=True,
        max_merged_images=4,
        send_video_as_file=True,
    )


class BoomEvent(FakeVideoEvent):
    """模拟本地文件视频消息失败，但文本兜底仍可用的一次性事件。"""

    def __init__(self):
        super().__init__()
        self.failed_once = False

    async def send(self, result):
        if not self.failed_once:
            self.failed_once = True
            raise RuntimeError("no local file support")
        self.sent.append(result)


async def video_modes():
    video_file = TMP_ROOT / "_tmp_data" / "v.mp4"
    video_file.write_bytes(b"0" * 4096)

    event = FakeVideoEvent()
    sender = make_sender(FakeStreamClient(), "local")
    await sender._try_local_video_message(event, video_file, "u")
    check("local 本地发送可用", len(event.sent) == 1)

    client = FakeStreamClient()
    sender = make_sender(client, "local")
    boom = BoomEvent()
    await sender._send_video(boom, video_file, "u")
    check("local 模式不回退流式上传", client.calls == 0, f"calls={client.calls}")
    check("local 失败有提示", len(boom.sent) == 1, str(boom.sent))

    client = FakeStreamClient()
    sender = make_sender(client, "stream")
    boom = BoomEvent()
    await sender._send_video(boom, video_file, "u")
    check("stream 模式优先尝试流式", client.calls == 1, f"calls={client.calls}")

    client = FakeStreamClient()
    sender = make_sender(client, "auto")
    sender.stream_threshold_bytes = 10 * 1024 * 1024
    boom = BoomEvent()
    await sender._send_video(boom, video_file, "u")
    check("auto 小文件失败后回退流式", client.calls == 1, f"calls={client.calls}")

    client = FakeStreamClient()
    sender = make_sender(client, "auto")
    sender.stream_threshold_bytes = 1
    event = FakeVideoEvent()
    await sender._send_video(event, video_file, "u")
    check("auto 大文件先流式再本地", client.calls == 1 and len(event.sent) == 1, f"calls={client.calls}")

    client = FakeStreamClient()
    client.status = "stream"
    sender = make_sender(client, "auto")
    sender.stream_threshold_bytes = 1
    event = FakeVideoEvent()
    await sender._send_video(event, video_file, "u")
    check("流式成功不再重复本地发送", len(event.sent) == 0, f"sent={len(event.sent)}")


asyncio.run(video_modes())

print("\n== 流式上传分块 ==")
from xparser_plugin.core.onebot_stream_client import OneBotStreamClient as SC


class FakeBot:
    def __init__(self):
        self.payloads = []

    async def upload_file_stream(self, **payload):
        self.payloads.append(payload)
        if payload.get("is_complete"):
            return {"data": {"file": "/uploaded/x.mp4"}}
        return {}


class FakeStreamEvent:
    def __init__(self):
        self.bot = FakeBot()

    def get_platform_name(self):
        return "aiocqhttp"


async def stream_test():
    data = b"a" * (600 * 1024)
    path = TMP_ROOT / "_tmp_data" / "s.mp4"
    path.write_bytes(data)
    client = SC(max_bytes=10 * 1024 * 1024)
    event = FakeStreamEvent()
    uploaded = await client.upload_file_stream(event, path)
    payloads = event.bot.payloads
    check("流式上传返回路径", uploaded == "/uploaded/x.mp4", str(uploaded))
    chunk_payloads = [p for p in payloads if not p.get("is_complete")]
    check("分块数量正确", len(chunk_payloads) == 2, str(len(chunk_payloads)))
    import hashlib

    digest = hashlib.sha256(data).hexdigest()
    check("每个分块都带 sha256", all(p["expected_sha256"] == digest for p in chunk_payloads))
    check("完成包带 sha256", payloads[-1]["expected_sha256"] == digest)
    check("未知动作回退 call_action", True)


asyncio.run(stream_test())

print("\n== X API 类型化异常 ==")
from xparser_plugin.core.x_api_client import (
    XApiClient,
    XApiError,
    XApiForbiddenError,
    XApiNotFoundError,
)

check("NotFound 兼容 ValueError", isinstance(XApiNotFoundError("x", 404), ValueError))
check("NotFound 兼容 FileNotFoundError", isinstance(XApiNotFoundError("x", 404), FileNotFoundError))
check("Forbidden 兼容 ValueError", isinstance(XApiForbiddenError("x", 403), ValueError))
check("XApiError 记录状态码", XApiError("x", 402).status_code == 402)

client = XApiClient(bearer_token="t", enable_proxy=False)
check("OAuth1 不可用时不误判", client.oauth1_available is False)
check("Cookie 不可用时不误判", client.cookie_available is False)
header = client._generate_oauth1_header(
    "GET", "https://api.x.com/2/tweets/1", {"expansions": "author_id"}
)
check("OAuth 头含签名", "oauth_signature=" in header, header[:60])


async def notfound_test():
    client = XApiClient(bearer_token="t", enable_proxy=False)

    async def fake_make_request(*args, **kwargs):
        raise XApiNotFoundError("❌ 目标资源不存在 (404)：Not Found", status_code=404)

    client._make_request = fake_make_request
    try:
        await client.get_tweet("123")
        check("get_tweet 404 -> FileNotFoundError", False, "no exception")
    except FileNotFoundError:
        check("get_tweet 404 -> FileNotFoundError", True)
    except Exception as exc:  # noqa: BLE001
        check("get_tweet 404 -> FileNotFoundError", False, f"got {type(exc).__name__}")

    async def fake_forbidden(*args, **kwargs):
        raise XApiForbiddenError("❌ 403", status_code=403)

    client._make_request = fake_forbidden
    try:
        await client.get_trends(1)
        check("get_trends 403 -> 降级提示", False, "no exception")
    except ValueError as exc:
        check("get_trends 403 -> 降级提示", "趋势获取失败" in str(exc), str(exc)[:40])

    async def fake_ok(*args, **kwargs):
        return {"data": {"data": [{"trend_name": "tag", "tweet_count": 3}]}, "headers": {}}

    client._make_request = fake_ok
    trends = await client.get_trends(1)
    check(
        "get_trends 成功路径不误抛",
        trends.data is not None and trends.data[0].trend_name == "tag",
        str(trends.data),
    )

    # 404 之外的 4xx 不应被误判为「推文不存在」
    async def fake_429(*args, **kwargs):
        raise XApiError("⚠️ 速率限制", status_code=429)

    client._make_request = fake_429
    try:
        await client.get_tweet("123")
        check("429 不被当作 404", False, "no exception")
    except FileNotFoundError:
        check("429 不被当作 404", False, "误判为 FileNotFoundError")
    except XApiError:
        check("429 不被当作 404", True)


asyncio.run(notfound_test())

print("\n== 配置项敏感标记 ==")
import json

schema = json.loads((TMP_ROOT / PLUGIN_PKG / "_conf_schema.json").read_text(encoding="utf-8"))
auth_items = schema["auth"]["items"]
credential_keys = [k for k in auth_items if k != "graphql_tweet_query_id"]
check(
    "认证凭据全部使用 secret 标记",
    all(auth_items[k].get("secret") is True for k in credential_keys),
    str([k for k in credential_keys if not auth_items[k].get("secret")]),
)
check("不再包含无效的 is_sensitive", "is_sensitive" not in json.dumps(schema))

print("\n================ 结果 ================")
if failures:
    for item in failures:
        print("FAILED:", item)
    sys.exit(1)
print("全部自检通过")
