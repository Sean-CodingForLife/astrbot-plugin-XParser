# 更新日志

本文档记录 `astrbot-plugin-XParser` 的主要变更。

## [0.1.0] - 2026-07-08

### 新增

- 初版 AstrBot 插件框架，支持解析 X/Twitter 推文链接
- 自动识别 `x.com` 与 `twitter.com` 推文链接
- `/xparse <tweet-url>` 手动解析命令
- X API Bearer Token / OAuth 1.0a / Cookie GraphQL 降级解析
- 推文文字、作者、时间、互动数据、图片、视频、GIF 提取
- 图片下载与压缩流程
- 基于当前内置 OneBot 发送适配器的视频流式上传与发送
- 视频消息失败后的文件回退能力
- 会话冷却、重复推文冷却、黑白名单访问控制
- 可配置的推文输出模板
- 可配置的图片压缩、视频变体选择、本地缓存保留时间

### 发送链路

- 图片发送改为三层回退：
  - 原始图片 URL
  - 临时媒体 HTTP URL
  - `base64://`
- 视频 / GIF 统一接入 URL / HTTP 兜底：
  - 原始视频 URL
  - 临时媒体 HTTP URL
  - 直接发送 / 流式上传 / 文件回退

### 临时媒体 HTTP 服务

- 新增插件自建临时媒体 HTTP 服务
- 支持临时 token、TTL、按路径返回文件流
- 支持通过 `transport.temp_media_http_host` 和 `transport.temp_media_http_port` 配置监听地址与端口
- `transport.temp_media_base_url` 改为只表达访问主机地址，未显式填写端口时自动拼接 `temp_media_http_port`
- 图片、视频、GIF 都可使用临时媒体 HTTP URL 作为兜底层

### 日志与排错

- 增加临时媒体 HTTP 服务启动失败日志
- 增加图片 `source / temp HTTP / base64` 三层发送链路日志
- 增加视频 / GIF `source / temp HTTP / 回退链路` 日志
- 增加临时媒体 URL 生成失败日志
- 增加流式上传缺少 bot 客户端、文件不存在等提示日志

### 文档

- 重写 `README.md`，改为面向中文用户说明
- 补充插件信息、适配平台、版本要求、当前定位与限制说明
- 调整配置说明，明确：
  - `6190` 是插件临时媒体 HTTP 服务端口
  - `temp_media_base_url` 默认不再直接暴露端口
  - 插件运行时会自动拼接端口

### 元信息

- 更新插件描述，明确当前版本内置 OneBot 发送适配器
- 明确 AstrBot 最低版本要求为 `>= 4.0.0`
