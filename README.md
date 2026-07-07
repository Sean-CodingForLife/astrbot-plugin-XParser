# astrbot-plugin-XParser

XParser 是一个面向 AstrBot + NapCat 部署的 X/Twitter 推文解析插件。它可以自动识别聊天中的推文链接，提取推文文本、作者、时间、互动数据、图片、视频和 GIF，并通过 NapCat 发送到 QQ。

本项目重点解决一个常见部署痛点：**AstrBot 和 NapCat 分别运行在不同容器中，且没有共享目录**。在这种情况下，传统的本地文件路径发送会失败，XParser 会使用 NapCat Stream API 将视频跨容器传递给 NapCat，再由 NapCat 发送视频消息。

## 功能特性

- 自动识别 `x.com/.../status/...` 和 `twitter.com/.../status/...` 推文链接。
- 支持 `/xparse <推文链接>` 手动解析。
- 提取推文文本、作者、发布时间、点赞/转发/回复数。
- 支持图片、视频、GIF 媒体解析。
- 推文文字摘要支持自定义输出模板。
- 图片在 NapCat/OneBot 场景下使用 `base64://` 发送，避免共享目录依赖。
- 支持普通消息、QQ 合并转发两种发送样式，并可单独控制图文是否合并。
- 图片压缩可配置：是否启用、目标大小、固定质量或目标体积模式。
- 视频质量可配置：在 X/Twitter 提供的 MP4 变体中选择最高、中等或最低体积。
- 视频优先通过 NapCat `upload_file_stream` 跨容器传输，再作为 QQ 视频消息发送。
- 视频消息失败时可自动退化为群文件/私聊文件。
- 支持 X API Bearer Token、OAuth 1.0a、Cookie GraphQL 降级解析。
- 带有本地缓存 TTL 清理机制。

## 适配范围

| 项目 | 当前适配情况 |
|---|---|
| 插件版本 | `v0.1.0` |
| AstrBot | `>= 4.0.0`，当前开发与测试环境覆盖 AstrBot `v4.26.4` |
| 适配器平台 | `aiocqhttp` / OneBot v11 |
| QQ 客户端侧 | NapCatQQ，推荐 `v4.8.115+`，因为 Stream API 从该版本开始引入 |
| 媒体发送链路 | 图片：OneBot `base64://`；视频/GIF：NapCat `upload_file_stream` + OneBot 视频消息 |
| 聊天场景 | QQ 群聊、QQ 私聊 |
| 解析来源 | `x.com`、`twitter.com` 推文详情页链接 |
| 部署方式 | 优先适配 AstrBot 与 NapCat 分容器、无共享目录的 Docker 部署；同机或共享目录部署可使用 `local` 模式 |

当前没有专门适配 Telegram、Discord、微信、KOOK 等非 OneBot 平台。插件里的 Stream API 能力依赖 NapCat 的 OneBot action，因此其他 OneBot 实现即使能发文字和图片，也不一定支持视频跨容器上传。

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

发送样式选择为 `普通消息` 且开启“合并发送文字和图片”后，图片推文会尽量按下面的形式发送：

```text
推文文字摘要 + 图片 1 + 图片 2 + ...
```

发送样式选择为 `合并转发` 后，插件会尝试发送 QQ 合并聊天记录：

```text
合并转发消息
  节点 1：推文文字摘要
  节点 2：图片 1
  节点 3：图片 2
  节点 4：视频/GIF 提示
```

视频仍会单独发送，因为 QQ/OneBot 对“文字 + 图片 + 视频”混合消息以及合并转发内的视频节点兼容性较差。如果合并转发发送失败，插件会自动退回普通消息样式；回退后是否图文合并，由“合并发送文字和图片”开关决定。

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

## 输出模板

配置项：

```text
tweet_text_template
```

默认模板：

```text
{author}

{text}

时间：{created_at}{metrics_line}{media_summary_line}
链接：{url}
```

可用占位符：

| 占位符 | 含义 |
|---|---|
| `{author}` | 作者展示，例如 `@username (昵称)` |
| `{author_name}` | 作者昵称 |
| `{author_username}` | 作者用户名，不含 `@` |
| `{tweet_id}` | 推文 ID |
| `{text}` | 推文正文 |
| `{created_at}` | 发布时间 |
| `{like_count}` | 点赞数 |
| `{retweet_count}` | 转发数 |
| `{reply_count}` | 回复数 |
| `{metrics_line}` | 已格式化的互动行 |
| `{media_summary}` | 媒体摘要，例如 `2 张图片，1 个视频` |
| `{media_summary_line}` | 已格式化的媒体摘要行 |
| `{url}` | 推文链接 |

如果模板里写了不存在的占位符，插件会回退到默认模板并写入日志。

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

## 发送样式

配置项：

```text
send_mode = 普通消息 | 合并转发
```

| 样式 | 显示效果 | 说明 |
|---|---|---|
| `普通消息` | 普通 QQ 消息 | 兼容性最好。图片是否和文字合并，由 `merge_text_and_images` 开关决定。 |
| `合并转发` | QQ 合并聊天记录 | 尝试把文字和图片作为多个节点展示；视频仍单独发送。失败时自动退回 `普通消息`。 |

图文合并开关：

```text
merge_text_and_images = true | false
```

开启后，普通消息样式会尽量把推文文字和图片放进同一条消息；关闭后，插件会先发文字，再逐张发送图片。视频/GIF 始终单独发送。

## 冷却与访问控制

冷却配置：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `cooldown_seconds` | `10` | 同一个群聊或同一个私聊，两次解析之间的最小间隔。 |
| `same_tweet_cooldown_seconds` | `120` | 同一个会话里重复解析同一条推文的最小间隔。 |

自动解析触发冷却时会静默忽略，避免群聊继续刷屏；手动 `/xparse` 触发冷却时会提示剩余秒数。填 `0` 表示关闭对应冷却。

访问控制配置：

```text
acl_mode = 关闭 | 白名单 | 黑名单
```

| 模式 | 说明 |
|---|---|
| `关闭` | 所有群聊和私聊都允许使用。 |
| `白名单` | 只允许白名单里的群号/用户 QQ 使用；对应名单为空时不限制对应场景。 |
| `黑名单` | 禁止黑名单里的群号/用户 QQ 使用。 |

名单配置：

| 配置项 | 填写内容 |
|---|---|
| `allowed_group_ids` | 群聊白名单，填写允许使用的群号。 |
| `allowed_private_user_ids` | 私聊白名单，填写允许使用的用户 QQ。 |
| `blocked_group_ids` | 群聊黑名单，填写禁止使用的群号。 |
| `blocked_private_user_ids` | 私聊黑名单，填写禁止使用的用户 QQ。 |

访问控制对自动解析和 `/xparse` 都生效。自动解析被访问控制拦截时会静默忽略，手动命令被拦截时会提示当前会话不在允许范围内。

## 压缩策略

### 图片压缩

图片使用 Pillow/PIL 压缩，不依赖外部命令。

支持两种模式：

| 模式 | 说明 |
|---|---|
| `target_size` | 尽量压缩到目标 KB 以内，并保留满足体积要求的最高质量 |
| `quality` | 按固定质量重新保存，不强求目标体积 |

关键配置：

- `enable_image_compression`: 是否启用图片压缩。
- `image_compress_mode`: `target_size` 或 `quality`。
- `image_compress_quality`: 质量参数，范围 1-100，默认 85。
- `image_compress_target_kb`: 目标大小，默认 2048KB。

GIF 动图不会用 PIL 压缩，以避免破坏帧序列。

### 视频质量选择

当前版本**不会使用 ffmpeg 重新编码视频**。原因是 ffmpeg 会增加部署依赖、CPU 占用和发送延迟。

插件会在 X/Twitter 返回的 MP4 variants 中选择一个直链：

| 策略 | 说明 |
|---|---|
| `highest` | 选择最高码率，画质最好，体积最大 |
| `balanced` | 选择中间档，画质和体积折中 |
| `lowest` | 选择最低码率，体积最小，画质最低 |

配置项：

```text
video_variant_strategy = highest | balanced | lowest
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
