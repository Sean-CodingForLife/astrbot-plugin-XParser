# 更新日志

本文档记录 `astrbot-plugin-XParser` 的主要变更。

## [0.1.1] - 2026-07-08

### 修复

- 修复 `@register` 装饰器参数顺序错误（作者与简介位置互换），避免插件元数据错位
- 修复 `temp_media_base_url` 端口非法（如 `http://astrbot:abc`）时插件初始化直接抛错的问题，现在会忽略该端口并回退到 `transport.temp_media_http_port`
- 修复显式端口与 `transport.temp_media_http_port` 一致时仍反复提示端口配置的问题，改为仅在不一致时告警
- 修复自动解析推文后事件继续传播、导致同一条消息被 LLM 再回复一次的问题
- 修复图片媒体被视频变体逻辑误改 URL 的问题（现仅对视频 / GIF 做变体择优）
- 修复图片落盘扩展名固定为 `.jpg`、导致实际编码与扩展名 / MIME 不一致（例如 PNG 图片被标成 image/jpeg）的问题
- 修复媒体缓存文件名使用进程级随机 `hash()`、进程重启后文件名不稳定的问题，改用 SHA-1 摘要
- 修复 `local` 视频投递策略仍会回退到流式上传、与配置说明不符的问题
- 修复视频投递链路的分支冗余，以及 `auto` 模式下大文件回退顺序说明不清的问题
- 修复 `get_trends` 在 403 降级分支后残留 `else: raise` 导致成功路径也可能抛错的问题
- 修复 404 / 403 依靠错误文案字符串匹配判断的问题，改为类型化异常（`XApiNotFoundError` / `XApiForbiddenError`）

### 优化

- 流式上传改为边读边发，不再把整个视频读进内存
- 流式上传增加状态返回（`stream` / `file` / `stream_failed` / `skipped`），供发送链路精确决策
- `_conf_schema.json` 敏感项改用 AstrBot 支持的 `secret` 字段（原 `is_sensitive` 不生效）
- 移除 `initialize()` 中无效的过期清理调用与不可达代码

### 测试

- 新增 `tests/selfcheck.py` 离线自检脚本（桩模块加载插件，无需安装 AstrBot）
- 覆盖推文链接识别、图片格式与落盘扩展名、视频投递策略、
  流式上传分块、404 / 403 错误分类与趋势成功路径

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
- 合并转发节点新增 UIN 策略：
  - `bot`：优先使用机器人自身 QQ 号
  - `fixed`：使用自定义 UIN，并给出风险警告
  - `default`：固定使用 `10000`

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
