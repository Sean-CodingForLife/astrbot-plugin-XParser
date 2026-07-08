# astrbot-plugin-XParser

XParser 是一个面向 AstrBot + NapCat 部署的 X/Twitter 推文解析插件。它可以自动识别聊天中的推文链接，提取推文文字、作者、时间、互动数据、图片、视频和 GIF，并发送到 QQ。

插件重点解决的就是 AstrBot 和 NapCat 分容器部署时的媒体发送问题，尤其是不共享文件目录时的跨容器传输。

## 功能

- 自动识别 `x.com/.../status/...` 和 `twitter.com/.../status/...`
- 支持 `/xparse <tweet-url>` 手动解析
- 提取推文文本、作者、发布时间、点赞/转发/回复数
- 支持图片、视频、GIF 解析
- 支持 X API Bearer Token、OAuth 1.0a、Cookie GraphQL 降级解析
- 支持普通消息和 QQ 合并转发两种发送样式
- 支持图片压缩、视频变体择优、本地缓存 TTL 清理
- 支持会话冷却、重复推文冷却、群聊/私聊白名单与黑名单

## 当前媒体发送链路

### 图片

图片现在按三层顺序发送：

1. 原始图片 URL 直发
2. HTTP 临时媒体 URL 兜底
3. `base64://` 最终兜底

说明：

- HTTP 临时媒体仅用于图片
- 如果 AstrBot 当前环境无法注册 HTTP 路由，或 NapCat 无法访问该地址，插件会自动跳过 HTTP 层
- 默认提供 `temp_media_base_url = http://astrbot:6185`
- 如需完全关闭 HTTP 兜底，可关闭 `enable_temp_media_http_fallback`

### 视频 / GIF

视频和 GIF 不走 HTTP 临时媒体服务，保持和当前实现一致：

1. 根据 `media_transfer_mode` 选择本地发送或 Stream API 优先策略
2. 失败后走 NapCat Stream API 上传
3. 视频消息仍失败时，再按配置决定是否回退为群文件或私聊文件

## 适配范围

| 项目 | 当前情况 |
|---|---|
| 插件版本 | `v0.1.0` |
| AstrBot | `>= 4.0.0` |
| 适配器 | `aiocqhttp` / OneBot v11 |
| QQ 侧 | NapCat |
| 聊天场景 | QQ 群聊、QQ 私聊 |
| 图片链路 | 原始 URL -> HTTP 临时 URL -> `base64://` |
| 视频链路 | 本地视频组件 / NapCat `upload_file_stream` / 文件兜底 |

## 项目结构

```text
main.py                         AstrBot 入口与主流程
core/x_api_client.py            X/Twitter API 与 Cookie GraphQL 请求
core/media_processor.py         媒体下载、图片压缩、视频变体选择
core/access_control.py          冷却、群聊/私聊黑白名单
core/napcat_stream_client.py    NapCat Stream API 分片上传
core/temp_media_registry.py     HTTP 临时媒体 token 注册表与 TTL
core/temp_media_server.py       HTTP 临时媒体路由与文件流返回
adapters/onebot_napcat.py       QQ/OneBot/NapCat 发送适配
models/                         X/Twitter 响应模型
```

## 基本配置

优先配置这些项即可：

- `auth.api_bearer_token`
- `auth.cookie_auth_token`
- `auth.cookie_ct0`
- `send.media_transfer_mode`

推荐默认值：

- `send.media_transfer_mode = auto`
- `send.enable_temp_media_http_fallback = true`
- `send.temp_media_base_url = http://astrbot:6185`
- `send.temp_media_path_prefix = /xparser/media`
- `send.temp_media_ttl_seconds = 300`

如果你的 compose 网络里 NapCat 可以通过 `http://astrbot:6185` 访问 AstrBot，那么图片 HTTP 兜底开箱即用。

如果你的服务名或端口不同，修改：

```text
send.temp_media_base_url
```

如果你不想使用 HTTP 兜底，关闭：

```text
send.enable_temp_media_http_fallback = false
```

## Docker / 容器说明

默认 `temp_media_base_url` 使用的是：

```text
http://astrbot:6185
```

这表示：

- `astrbot` 是 docker compose 服务名
- `6185` 是 AstrBot 容器内监听端口
- 这里用的是容器间网络地址，不是宿主机 `127.0.0.1:6185`

如果你的容器内实际监听端口不是 `6185`，或者服务名不是 `astrbot`，按实际情况修改这个值。

## 输出模板

默认模板：

```text
{author}

{text}

时间：{created_at}{metrics_line}{media_summary_line}
链接：{url}
```

可用占位符：

- `{author}`
- `{author_name}`
- `{author_username}`
- `{tweet_id}`
- `{text}`
- `{created_at}`
- `{like_count}`
- `{retweet_count}`
- `{reply_count}`
- `{metrics_line}`
- `{media_summary}`
- `{media_summary_line}`
- `{url}`

## 传输模式

| 模式 | 说明 |
|---|---|
| `auto` | 小视频优先本地视频消息，较大视频或失败后走 Stream API |
| `stream` | 视频强制优先走 Stream API |
| `local` | 视频只走本地文件路径发送 |

对 AstrBot / NapCat 分容器部署，推荐：

```text
auto
```

## 已知事实

- 图片 HTTP 临时媒体服务已经落地，不再是规划项
- HTTP 临时媒体服务当前只用于图片，不用于视频
- HTTP 路由注册能力取决于当前 AstrBot 运行环境；如果不可用，插件会自动回退，不影响主链路

## 常见问题

### 为什么图片有时还是会走 `base64://`？

因为三层链路是逐层尝试的：

- 原始 URL 发不出去
- 或 HTTP 临时 URL 当前不可用
- 最终才回退到 `base64://`

这属于预期行为。

### 为什么视频没有走 HTTP 临时服务？

这是当前设计决定。视频仍按现有视频链路处理，没有接入 HTTP 临时媒体服务。

### HTTP 临时媒体服务一定可用吗？

不一定。

它是兜底能力，不是硬依赖。只要下面任一条件不满足，就会自动跳过：

- AstrBot 运行环境支持挂载 HTTP 路由
- NapCat 能访问 `temp_media_base_url`

## 状态

当前版本已经包含：

- 推文文本解析
- 图片解析与三层发送链路
- 视频 / GIF 解析与 NapCat Stream API 兜底
- Cookie GraphQL 降级
- 访问控制与缓存清理

后续如果继续扩展，优先方向会是：

- 补真实运行环境下的 HTTP 路由兼容性验证
- 为图片 HTTP 兜底增加更明确的运行日志
- 视需要再考虑视频 HTTP 方案
