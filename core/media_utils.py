"""媒体格式嗅探与文件名工具。

X/Twitter 的图片直链（pbs.twimg.com）经常不带扩展名，或者以 `?format=png`
这类查询参数表达真实格式；而插件下载后会重新编码（例如统一转成 JPEG），
因此不能直接复用下载 URL 的扩展名。这里统一通过文件头魔数判断真实格式，
保证落盘文件扩展名与内容类型一致，避免 OneBot 侧按扩展名猜 MIME 时出错。
"""

from __future__ import annotations

from pathlib import Path

# 扩展名 -> MIME 类型
IMAGE_MIME_BY_EXT: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

# (魔数, 扩展名) 探测表
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"BM", ".bmp"),
)


def sniff_image_extension(data: bytes | None) -> str | None:
    """根据文件头魔数探测图片格式，未识别时返回 None。"""
    if not data:
        return None
    for signature, extension in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return extension
    # WebP: RIFF....WEBP
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def guess_image_extension(data: bytes | None, fallback: str = ".jpg") -> str:
    """探测图片扩展名，未知格式时回退到 fallback。"""
    return sniff_image_extension(data) or fallback


def image_mime_for_path(path: Path, fallback: str = "application/octet-stream") -> str:
    """按文件扩展名推断图片 MIME 类型。"""
    return IMAGE_MIME_BY_EXT.get(path.suffix.lower(), fallback)
