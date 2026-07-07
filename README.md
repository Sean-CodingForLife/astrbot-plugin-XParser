# astrbot-plugin-XParser

XParser 是一个面向 AstrBot + NapCat 部署的 X/Twitter 推文解析插件。它可以自动识别聊天中的推文链接，提取推文文本、作者、时间、互动数据、图片、视频和 GIF，并通过 NapCat 发送到 QQ。

本项目重点解决一个常见部署痛点：**AstrBot 和 NapCat 分别运行在不同容器中，且没有共享目录**。在这种情况下，传统的本地文件路径发送会失败，XParser 会使用 NapCat Stream API 将视频跨容器传递给 NapCat，再由 NapCat 发送视频消息。

## 功能特性

- 自动识别 `x.com/.../status/...` 和 `twitter.com/.../status/...` 推文链接。
- 支持 `/xparse <推文链接>` 手动解析。
- 提取推文文本、作者、发布时间、点赞/转发/回复数。
- 支持图片、视频、GIF 媒体解析。
- 图片在 NapCat/OneBot 场景下使用 `base64://` 发送，避免共享目录依赖。
- 视频优先通过 NapCat `upload_file_stream` 跨容器传输，再作为 QQ 视频消息发送。
- 视频消息失败时可自动退化为群文件/私聊文件。
- 支持 X API Bearer Token、OAuth 1.0a、Cookie GraphQL 降级解析。
- 带有本地缓存 TTL 清理机制。

## 工作原理

```text
QQ 消息
  ↓
AstrBot 事件监听
  ↓
提取推文 ID
  ↓
X API / Cookie GraphQL 获取推文详情
  ↓
发送文本摘要
  ↓
图片：下载 -> 压缩 -> base64:// -> OneBot 图片消息
视频：下载 -> Stream API 分片上传 -> NapCat 临时路径 -> OneBot 视频消息
```

### 为什么需要 Stream API

如果 AstrBot 和 NapCat 在不同容器中，AstrBot 下载的视频路径类似：

```text
/AstrBot/data/plugin_data/astrbot_plugin_xparser/videos/xxx.mp4
```

NapCat 容器无法访问这个路径，因此普通本地文件发送会出现：

```text
ENOENT: no such file or directory
```

XParser 会将视频切成分片，通过 NapCat `upload_file_stream` 传给 NapCat。NapCat 合并后返回自己的临时路径，例如：

```text
/app/.config/QQ/NapCat/temp/xxx.mp4
```

随后插件再用该路径发送 OneBot `video` 消息。

## 安装

在 AstrBot 插件管理页面使用仓库地址安装：

```text
https://github.com/Sean-CodingForLife/astrbot-plugin-XParser.git
```

依赖由 AstrBot 插件系统根据 `requirements.txt` 安装：

```text
httpx[http2]>=0.26.0
Pillow>=10.1.0
pydantic>=2.5.0
```

## 基本配置

推荐先填写：

- `X API Bearer Token`
- `Cookie 降级认证：auth_token`
- `Cookie 降级认证：ct0`
- `媒体传输模式`: `auto`

如果你的 X API 额度不足，日志里出现：

```text
API 返回 402（账户额度耗尽），尝试 Cookie 降级认证
```

说明 Bearer/OAuth 额度已经不够，插件会使用 `auth_token` + `ct0` 走 Cookie GraphQL 降级。

## 传输模式

| 模式 | 说明 | 推荐场景 |
|---|---|---|
| `auto` | 小视频先尝试普通消息，失败或较大视频走 Stream API | 默认推荐 |
| `stream` | 视频强制走 NapCat Stream API | AstrBot/NapCat 分容器且无共享目录 |
| `local` | 只使用本地文件路径组件 | AstrBot 和 NapCat 同机或共享目录 |

对当前双容器部署，推荐使用：

```text
auto
```

如果你确定本地路径一定不可用，可以改为：

```text
stream
```

## 缓存策略

AstrBot 侧缓存目录：

```text
/AstrBot/data/plugin_data/astrbot_plugin_xparser/images/
/AstrBot/data/plugin_data/astrbot_plugin_xparser/videos/
```

默认配置：

```text
cache_ttl_hours = 24
```

插件启动或重载时会清理超过 TTL 的本地缓存。当前没有后台定时清理任务，后续会加入周期性清理。

NapCat 侧 Stream API 临时文件通常位于 NapCat 自己的临时目录，例如：

```text
/app/.config/QQ/NapCat/temp/
```

后续计划在视频发送成功后调用 `clean_stream_temp_file` 主动清理。

## 常见问题

### 插件更新时报 repository URL 缺失

旧版本 `metadata.yaml` 没有 `repo` 字段时，AstrBot 无法通过“更新插件”按钮找到下载地址。解决方式：

1. 卸载旧插件。
2. 用仓库地址重新安装。

新版本已经包含：

```yaml
repo: https://github.com/Sean-CodingForLife/astrbot-plugin-XParser
```

### 插件更新时报 All connection attempts failed

这是 AstrBot 容器连接 GitHub 失败，不是插件代码问题。可以：

- 重试更新。
- 给 AstrBot 插件更新功能配置代理。
- 确认容器内能访问 `github.com`。

### 视频为什么先报 ENOENT 又成功

在 `auto` 模式下，插件可能先尝试普通本地路径视频发送。双容器无共享目录时，这一步会失败：

```text
ENOENT: no such file or directory
```

随后插件会自动走 Stream API。只要后面出现：

```text
NapCat Stream video sent as video message
```

就说明最终发送成功。

### 为什么视频比图片慢

视频链路更长：

```text
下载视频 -> 写入缓存 -> 分片上传 NapCat -> NapCat 合并 -> QQ 发送视频
```

后续可优化方向：

- 在 aiocqhttp/NapCat 平台下直接走 Stream API，跳过必定失败的本地路径尝试。
- 调大 Stream 分片大小，减少请求次数。
- 引入 AstrBot 临时 HTTP 服务，让 NapCat 直接拉取媒体。

## 路线图

- [ ] 视频在 NapCat 平台下可配置为直接 Stream，不再先尝试本地路径。
- [ ] 视频发送成功后调用 `clean_stream_temp_file` 清理 NapCat 临时文件。
- [ ] AstrBot 侧增加后台定时缓存清理任务。
- [ ] 图片支持 URL 优先，失败后再退回 `base64://`。
- [ ] 探索 AstrBot 临时 HTTP 媒体服务。
- [ ] 探索 NapCat companion plugin，将媒体下载、发送、清理下沉到 NapCat 侧。

### AstrBot 临时 HTTP 媒体服务

这是一个未来重点方向。设计上，AstrBot 可以暴露短期有效的内网 HTTP URL，NapCat 从该 URL 拉取图片或视频。相比 `base64://`，它对图片更优雅；相比 Stream API，它对小文件更轻量。

但这个方案需要额外处理：

- URL 鉴权，避免媒体被外部访问。
- TTL 和一次性 token。
- Docker 网络连通性。
- 下载完成后的缓存清理。

## 项目状态

当前版本仍处于早期迭代阶段，但核心链路已经验证：

- 文本推文解析成功。
- 图片推文解析和发送成功。
- 视频推文通过 NapCat Stream API 发送为视频消息成功。
- X API 额度耗尽时 Cookie GraphQL 降级成功。

欢迎继续用真实群聊场景压测，尤其是大视频、多图、GIF、长文本推文和引用推文。
