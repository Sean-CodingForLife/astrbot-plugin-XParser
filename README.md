# astrbot-plugin-XParser

XParser 是一个用于 AstrBot 的 X/Twitter 推文解析插件。插件核心负责推文解析、媒体下载与兜底链路，当前内置的发送适配器为 OneBot。

## 插件信息

- 插件名：`astrbot_plugin_xparser`
- 显示名：`XParser`
- 当前版本：`v0.1.0`
- 作者：`seant`
- 仓库地址：[Sean-CodingForLife/astrbot-plugin-XParser](https://github.com/Sean-CodingForLife/astrbot-plugin-XParser)
- AstrBot 版本要求：`>= 4.0.0`

## 适配平台

- AstrBot 平台：当前按 `aiocqhttp` / OneBot 事件链路实现与测试
- 消息发送适配器：当前内置 `OneBotSender`
- 流式上传链路：当前按 OneBot 客户端可调用 `upload_file_stream` 一类动作的场景实现

## 当前定位

- 这是一个“解析核心 + 媒体投递链路 + 当前内置 OneBot 发送适配器”的插件
- 解析、下载、临时 HTTP 媒体服务这些能力可以继续复用到别的发送适配器
- 现阶段真正落地并完成发送链路实现的，只有 OneBot 这一套
- 如果未来接别的平台，优先应当继续复用 `core/`，只在 `adapters/` 里新增对应发送适配

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
- 支持基于当前内置 OneBot 发送适配器的视频流式上传
- 支持普通消息、合并转发两种发送方式
- 支持图片压缩、视频变体择优、本地缓存清理
- 支持会话冷却、重复推文冷却、黑白名单

## 当前已验证场景

- AstrBot 容器与发送适配器容器分离
- `docker compose` 桥接网络
- 不共享宿主文件目录
- 图片、GIF、视频都走统一的 URL / 临时 HTTP / 回退链路

## 当前未承诺范围

- 还没有内置 Telegram、Discord、KOOK 之类非 OneBot 发送适配器
- 还没有承诺所有 OneBot 实现都支持流式上传，是否可用取决于当前客户端是否提供对应动作
- 还没有做成“任意 AstrBot 平台适配器开箱即用”的通用发送层

## 媒体发送策略

### 图片

图片按三层顺序发送：

1. 原始图片 URL
2. 插件临时媒体 HTTP URL
3. `base64://`

### 视频 / GIF

视频和 GIF 现在也接入了统一的 URL / HTTP 兜底思路：

1. 原始视频 URL
2. 插件临时媒体 HTTP URL
3. 视频后续回退链路

视频后续回退链路为：

1. 按 `transport.media_transfer_mode` 决定优先直接发送还是流式上传
2. 直接发送失败时回退到流式上传链路
3. 视频消息仍失败时，再按配置决定是否回退为文件

## 临时媒体 HTTP 服务

插件可以额外启动一个小型 HTTP 服务，专门给当前发送适配器一侧拉取临时媒体。

关键点：

- 监听地址由 `transport.temp_media_http_host` 控制，默认 `0.0.0.0`
- 监听端口由 `transport.temp_media_http_port` 控制，默认 `6190`
- `transport.temp_media_base_url` 只表示访问主机地址，默认 `http://astrbot`
- 如果 `temp_media_base_url` 没写端口，插件会自动拼接 `temp_media_http_port`
- `transport.enable_temp_media_http_fallback` 是唯一 HTTP 总开关

## 合并转发节点

当发送样式选择“合并转发”时，下面这些设置才会生效：

- `send.forward_node_name`
  - 控制显示昵称
- `send.forward_node_uin_mode`
  - 控制节点 UIN 的来源策略
  - `bot`：优先使用机器人自己的 QQ 号，默认推荐
  - `fixed`：使用你手填的 `send.forward_node_uin`
  - `default`：固定使用 `10000`
- `send.forward_node_uin`
  - 仅在 `fixed` 模式下生效
  - 大多数客户端会根据这个 UIN 决定节点头像

如果当前发送样式是“普通消息”，上面这组三项会被直接忽略。

反过来也是一样：

- `send.merge_text_and_images`
- `send.max_merged_images`

这两项只在“普通消息”发送样式下生效；如果你切成“合并转发”，插件会忽略它们。

例如：

```text
send.send_mode = 合并转发
send.forward_node_name = X 推文解析
send.forward_node_uin_mode = bot
```

如果你明确要手动指定：

```text
send.send_mode = 合并转发
send.forward_node_name = X 推文解析
send.forward_node_uin_mode = fixed
send.forward_node_uin = 123456789
```

注意：

- 这不是直接上传自定义头像图片
- 默认推荐使用 `bot`，也就是直接使用机器人自己的 QQ 号
- `fixed` 模式虽然能更直接地换头像，但可能导致头像异常、显示异常或风控风险
- 实际头像是否变化，取决于当前 OneBot 客户端如何根据 `uin` 渲染转发节点

也就是说：

- 开启 `transport.enable_temp_media_http_fallback`
  - 插件会启动内置临时媒体 HTTP 服务
  - 媒体发送时会尝试 HTTP 临时 URL 这一层
- 关闭 `transport.enable_temp_media_http_fallback`
  - 插件不会启动临时媒体 HTTP 服务
  - 发送链路里也不会使用 HTTP 临时 URL

例如：

```text
transport.enable_temp_media_http_fallback = true
transport.temp_media_http_host = 0.0.0.0
transport.temp_media_http_port = 6190
transport.temp_media_base_url = http://astrbot
transport.temp_media_path_prefix = /xparser/media
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
- `transport.media_transfer_mode`

推荐值：

```text
transport.media_transfer_mode = auto
transport.enable_temp_media_http_fallback = true
transport.temp_media_http_host = 0.0.0.0
transport.temp_media_http_port = 6190
transport.temp_media_base_url = http://astrbot
transport.temp_media_path_prefix = /xparser/media
transport.temp_media_ttl_seconds = 300
```

如果你不想使用 HTTP 临时媒体服务与兜底：

```text
transport.enable_temp_media_http_fallback = false
```

## 容器部署说明

如果你用的是 `docker compose` 桥接网络，通常可以这样理解：

- `astrbot` 是 AstrBot 服务名
- 插件临时媒体服务跑在 AstrBot 容器内
- 发送适配器所在容器可通过 `http://astrbot:6190` 访问插件临时媒体服务

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
| `auto` | 小视频优先直接发送，失败或视频较大时切到流式上传 |
| `stream` | 强制优先走流式上传 |
| `local` | 只尝试本地文件视频消息 |

对于 AstrBot 与发送适配器分容器部署，推荐：

```text
auto
```

## 常见问题

### 为什么图片最后还是会走 `base64://`？

因为图片链路是逐层回退的：

- 原始图片 URL 发送失败
- 临时 HTTP 图片 URL 发送失败
- 最后才回退到 `base64://`

### 为什么视频 / GIF 没有直接成功？

视频 / GIF 现在会先尝试：

- 原始 URL
- 临时 HTTP URL

前两层都不行时，才会继续进入本地视频消息 / 流式上传 / 文件回退链路。

### 插件日志里应该看什么？

重点看这些日志：

- 推文解析是否成功
- 图片是否走了 `source` / `temp HTTP` / `base64`
- 视频 / GIF 是否走了 `source URL` / `temp HTTP` / `直接发送或流式上传回退`
- 临时媒体 HTTP 服务是否成功启动

如果临时 HTTP 服务启动失败，会提示你调整：

```text
transport.temp_media_http_port
transport.temp_media_base_url
```

## 项目结构

```text
main.py                         AstrBot 插件入口
core/x_api_client.py            X/Twitter API 与 Cookie GraphQL 请求
core/media_processor.py         媒体下载、图片压缩、视频变体选择
core/access_control.py          冷却与访问控制
core/onebot_stream_client.py    当前内置 OneBot 流式上传能力封装
core/temp_media_registry.py     临时媒体 token 注册表与 TTL
core/temp_media_server.py       插件自建临时媒体 HTTP 服务
adapters/onebot_sender.py       当前内置 OneBot 发送适配
models/                         X/Twitter 响应模型
```
