# astrbot-plugin-XParser

XParser 是一个用于 AstrBot 的 X/Twitter 推文解析插件，目标场景是 `AstrBot + NapCat` 部署，尤其是分容器、不共享文件目录的情况。

它可以自动识别聊天中的推文链接，提取：

- 推文文字
- 作者信息
- 发布时间
- 互动数据
- 图片
- 视频
- GIF

然后再发送到 QQ。

## 功能概览

- 自动识别 `x.com/.../status/...` 和 `twitter.com/.../status/...`
- 支持 `/xparse <tweet-url>` 手动解析
- 支持 X API、OAuth 1.0a、Cookie GraphQL 降级
- 支持图片、视频、GIF 提取与发送
- 支持 NapCat Stream API 视频上传
- 支持普通消息、合并转发两种发送方式
- 支持图片压缩、视频变体择优、本地缓存清理
- 支持会话冷却、重复推文冷却、黑白名单

## 媒体发送策略

### 图片

图片按三层顺序发送：

1. 原始图片 URL
2. 插件临时媒体 HTTP URL
3. `base64://`

也就是说，能直接发原图 URL 就直接发；原图 URL 不行，再尝试插件自己提供的临时 HTTP 地址；再不行才回退到 `base64://`。

### 视频 / GIF

视频和 GIF 现在也接入了统一的 URL / HTTP 兜底思路：

1. 原始视频 URL
2. 插件临时媒体 HTTP URL
3. 现有视频后备链路

现有视频后备链路为：

1. 按 `media_transfer_mode` 决定优先本地发送还是 Stream API
2. 本地发送失败时回退到 NapCat Stream API
3. 视频消息仍失败时，再按配置决定是否回退为文件

这套设计是为了适配 AstrBot 与 NapCat 不共享文件目录的场景。

## 临时媒体 HTTP 服务

插件可以额外启动一个小型 HTTP 服务，专门给 NapCat 拉取临时图片。

关键点：

- 监听地址由 `send.temp_media_http_host` 控制，默认 `0.0.0.0`
- 监听端口由 `send.temp_media_http_port` 控制，默认 `6190`
- `send.temp_media_base_url` 只表示访问主机地址，默认 `http://astrbot`
- 如果 `temp_media_base_url` 没写端口，插件会自动拼接 `temp_media_http_port`

例如：

```text
send.temp_media_http_host = 0.0.0.0
send.temp_media_http_port = 6190
send.temp_media_base_url = http://astrbot
send.temp_media_path_prefix = /xparser/media
```

运行时实际对外地址会变成：

```text
http://astrbot:6190/xparser/media/<token>
```

## 推荐配置

最少建议先配这些：

- `auth.api_bearer_token`
- `auth.cookie_auth_token`
- `auth.cookie_ct0`
- `send.media_transfer_mode`

推荐值：

```text
send.media_transfer_mode = auto
send.enable_temp_media_http_fallback = true
send.enable_temp_media_http_server = true
send.temp_media_http_host = 0.0.0.0
send.temp_media_http_port = 6190
send.temp_media_base_url = http://astrbot
send.temp_media_path_prefix = /xparser/media
send.temp_media_ttl_seconds = 300
```

如果你不想启用图片 HTTP 兜底：

```text
send.enable_temp_media_http_fallback = false
```

如果你不想让插件额外开 HTTP 服务：

```text
send.enable_temp_media_http_server = false
```

## 容器部署说明

如果你用的是 `docker compose` 桥接网络，通常可以这样理解：

- `astrbot` 是 AstrBot 服务名
- 插件临时媒体服务跑在 AstrBot 容器内
- NapCat 通过 `http://astrbot:6190` 访问插件临时媒体服务

这个插件不依赖 AstrBot 主 Web 服务端口本身，只依赖插件自己启动的临时媒体 HTTP 服务。

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

## 发送模式

| 模式 | 说明 |
|---|---|
| `auto` | 小视频优先本地视频消息，失败或视频较大时回退 Stream API |
| `stream` | 强制优先走 Stream API |
| `local` | 只尝试本地文件视频消息 |

对于 AstrBot / NapCat 分容器部署，推荐：

```text
auto
```

## 常见问题

### 为什么图片最后还是会走 `base64://`？

因为图片链路是逐层回退的：

- 原始图片 URL 发送失败
- 临时 HTTP 图片 URL 发送失败
- 最后才回退到 `base64://`

这属于预期行为。

### 为什么视频 / GIF 还是没有走临时 HTTP 服务？

因为视频 / GIF 现在虽然会先尝试原始 URL 和临时 HTTP URL，但只有在前面两层失败时，才会继续落到本地视频消息 / Stream API 链路。

所以你要看日志里是否出现：

- `Video/GIF sent via source URL ...`
- `Video/GIF sent via temp media HTTP ...`
- `Video/GIF source URL send failed ...`
- `Video/GIF temp media HTTP send failed ...`

### 插件日志里应该看什么？

重点看这些日志：

- 推文解析是否成功
- 图片是否走了 `source` / `temp HTTP` / `base64`
- 视频 / GIF 是否走了 `source URL` / `temp HTTP` / `本地或 Stream 回退`
- 临时媒体 HTTP 服务是否成功启动

如果临时 HTTP 服务启动失败，会提示你调整：

```text
send.temp_media_http_port
send.temp_media_base_url
```

## 项目结构

```text
main.py                         AstrBot 插件入口
core/x_api_client.py            X/Twitter API 与 Cookie GraphQL 请求
core/media_processor.py         媒体下载、图片压缩、视频变体选择
core/access_control.py          冷却与访问控制
core/napcat_stream_client.py    NapCat Stream API 上传
core/temp_media_registry.py     临时媒体 token 注册表与 TTL
core/temp_media_server.py       插件自建临时媒体 HTTP 服务
adapters/onebot_napcat.py       OneBot / NapCat 发送适配
models/                         X/Twitter 响应模型
```
