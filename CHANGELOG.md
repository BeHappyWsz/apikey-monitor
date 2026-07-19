# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 风格，版本号采用语义化版本。

## [Unreleased]

### Added

- Local administrator authentication with Argon2id password hashes, opaque
  HttpOnly sessions, CSRF protection, login throttling, bootstrap credentials
  from the private startup configuration, and administrator-created accounts.
- MySQL 8.0+ primary storage initialization (`keys`, `settings`, `users`, and
  `sessions`) plus an optional Redis 8.0+ read-through cache for masked
  API-key records and public settings.
- Cursor-paged key-list API (`GET /api/keys/page`) with server-side status and
  search filtering, masked rows, aggregate counters, and an opaque next-page
  cursor.
- Indexed monitor scheduling via persisted `next_check_at`, plus one shared
  outbound-probe concurrency budget across scheduled, manual, import, and
  batch checks.
- WebDAV sync-boundary regression coverage: remote payloads and replacement
  operations contain only portable API-key fields, leaving local settings and
  administrator accounts intact.

### Changed

- The key panel now loads 50 rows at a time and continues on scroll or an
  explicit “load more” action. Background revision checks no longer replace a
  scrolled list; they show a refresh prompt, while Refresh deliberately reloads
  the first page for the current filters.
- Monitoring now persists its next due time and applies deterministic jitter
  with status-aware backoff: degraded endpoints, rate limits, and rejected
  credentials are checked less aggressively without reducing protocol-status
  coverage for normal checks.
- 协议能力仅在对应协议本次探测成功（`up`）时展示；401/403、限流、异常或超时不再误判为支持。手动检测与后台监测都会全量刷新能力，失败后清除历史标志；无确认能力时面板显示“未确认”。
- Anthropic 能力探针改为可靠的真实生成探测：默认请求超时由 15s 提至 **45s**（慢/推理型网关一次 `/messages` 生成可达 5–37s 且偶发 502），并对瞬时失败（5xx / 超时 / 连接错误）最多重试 2 次（任一次 200 即成功），避免可用端点被误判为「不支持」、`supports_anthropic` 在 true/false 间横跳。设置页「请求超时」补充说明；现有库旧默认值 15 一次性迁移到 45。

### Fixed

- 云同步：在 WebDAV 设置弹窗动作按钮上方增加提示——修改服务器 / 用户名 / 远程路径后需先「保存设置」再上传或下载，否则上传与下载仍沿用上次保存的配置（上传按钮不会自动持久化表单，与「测试连接」不同）。

## [0.1.2] - 2026-07-17

相对 [0.1.1] 的 WebDAV 云同步发布版本。

### Added

- **可选 WebDAV 云同步**（坚果云等，对标 cc-switch）：设置页配置 server / 用户名 / 应用密码 / 远程路径；支持测试连接、上传、**下载合并**与**下载替换**（替换前自动本地备份一份）；**零第三方依赖**（`urllib` + Basic Auth + HTTPS）
- 同步载荷为可移植 JSON 信封 `{app, schema, exported_at, keys:[...]}`，复用备份字段（`name` / `base_url` / `api_key` / `check_model` / `check_path`）；下载兼容信封 / 裸数组 / 单对象三种形态
- WebDAV 凭据安全：应用密码以 `_webdav_password` 存于 DB，**不写入 `config.json`、不在设置接口明文返回**；远端错误信息对凭据脱敏
- 新增模块：`core/webdav.py`（纯 WebDAV 客户端）、`services/sync_service.py`（同步编排）、前端 `static/js/sync.js`

### Planned（可选增强，非承诺）

- 可选密钥落盘加密（仍依赖本机目录权限；非必做）
- 监测历史 / 告警等体验增强（按需）
- 第三协议端到端（如 Gemini）：待产品选型后再开任务
- WebDAV 体验增强：启动提示「云端有更新」、变更后提示上传、`MKCOL` 自动建目录、上传前「先拉再合再推」、端到端加密同步包（任务 `07-17-multi-device-webdav-sync`，Phase 1 已落地）
- 中期效率：thin list payload、按 id 局部 DOM 补丁、SQL 侧 due 过滤、问题状态再检策略、SSE 推送（见 `docs/design.md`）

## [0.1.1] - 2026-07-17

相对 [0.1.0] 的维护与效率增强版本。

### Added

- macOS / Linux 启动脚本 `start.sh`（`--no-browser`，可选 `--bg`，优先 `python3`）
- 系统设置打开时即显示 `0.0.0.0` 局域网风险提示；保存确认文案对齐
- 每条 Key 可选 **`check_path`**（仅相对路径）：覆盖 classify / health 探活默认入口；模型探测仍用内置 chat/messages 路径
- `check_path` 贯通：DB 迁移、API 校验、导入/导出 JSON、编辑页
- 列表 revision 短轮询：`GET /api/keys/revision`；前端 silent 刷新先比 revision 再拉全量

### Changed

- **`core.py` → `core/` 包**：保持 `import core` 稳定；新增 `PROTOCOL_PROBES` / `EXPORT_FORMATS` / `IMPORTERS` 注册表，便于后续扩展协议与导出格式
- **前端模块拆分**：`static/app.js` 瘦身为编排层；列表/卡片/导出/操作等拆到 `static/js/*`（行为不变）
- 文档收口：明确本机单用户定位；**不做** Web 访问密码 / 公网鉴权；路线图去掉误导项
- README / 设计文档 / 启动路径与 CHANGELOG 同步
- `config.json` 作为运行时设置的原子写入目标（页面改设置后落盘）
- 定时监测（`health_check`）仅探测已成功协议；首次/均未成功时全量；失败不兜底其它协议，保留 `supports_*`（手动检测仍全量 `classify`）
- 启动前单实例收敛：`.runtime/server.pid`；重复启动先停旧实例再 bind
- 监测效率：定时 `health_check` 不再附带 `model_check`（模型仅手动/classify）
- 监测调度：tick 防重叠（in-flight）、每 tick 上限 `concurrency×2`、due 按最久未检优先
- 默认列表刷新间隔 15s（仍可 0 关闭）
- 卡片整卡拖拽排序；移除拖拽手柄与卡片上 Codex/Claude 快捷按钮（导出仍走弹窗）

### Fixed

- 状态为 `up` 时清理残留探活错误：只聚合「最终胜出协议」的错误，避免 OpenAI-only 端点仍显示 Anthropic 404；`up` 卡片隐藏错误行；列表指纹纳入 `model_last_error`

## [0.1.0] - 2026-07-16

首个对外开源版本。

### Added

- 本地 API Key 管理：粘贴导入、手动添加、OpenAI / Anthropic 协议判别
- 定时监测：连通性、认证状态、延迟；全局与单条开关
- Web 管理：筛选、拖拽排序、编辑、批量检测 / 删除 / 导出
- 批量任务进度展示
- 配置导出：Claude Code、Codex CLI、`.env`、PowerShell、JSON；支持批量 JSON 与下载
- 列表刷新间隔可配置（监测设置，`0` 关闭主动轮询）
- 体验优化：工具栏「更多」、无选中禁用批量、`Ctrl+Enter` 保存、批量检测汇总与问题项筛选
- 列表卡片一键复制完整 API Key（`/api/keys/{id}/secret`）；列表接口脱敏
- JSON 备份 / 恢复：备份全部、导入识别同格式 JSON
- 空状态首次引导与导入示例
- 安全切换监听端口（失败回滚）
- 零第三方依赖（Python 3.10+ 标准库 + 现代浏览器）
- 基础单元测试与集成测试；CI 工作流示例（`docs/ci.workflow.example.yml`）
- MIT 许可证、README、CONTRIBUTING、CHANGELOG

### Security

- 列表与详情默认返回 `api_key_masked`，不暴露明文 Key
- 默认仅监听 `127.0.0.1`

### Changed

- JSON 导出字段精简为可移植配置：`name`、`base_url`、`api_key`、`check_model`
- 导出弹窗布局优化

[Unreleased]: https://github.com/BeHappyWsz/apikey-monitor/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/BeHappyWsz/apikey-monitor/releases/tag/v0.1.2
[0.1.1]: https://github.com/BeHappyWsz/apikey-monitor/releases/tag/v0.1.1
[0.1.0]: https://github.com/BeHappyWsz/apikey-monitor/releases/tag/v0.1.0
