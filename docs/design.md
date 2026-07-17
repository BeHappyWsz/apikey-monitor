# 项目设计文档

## 目标

构建一个零依赖、本地运行的 API Key 运维工具，覆盖 API Key 收集、解析、协议判别、定时连通性监测、Web 管理和配置导出。

## 非目标

- 不作为多用户 SaaS 系统。
- **不做 Web 登录 / 本地访问密码 / 公网鉴权**；信任模型是「本机单用户 + 默认 loopback + 操作系统文件权限」。
- 不实现细粒度权限模型与审计系统。
- 不替代专业密钥管理系统。
- 不主动消费大模型能力，只做低成本探活和协议识别。

## 架构

```text
Browser
  |
  | HTTP JSON
  v
app.py
  |-- static file server
  |-- REST-like API
  |-- sync classify / async batch classify
  |
  +--> core/  (package; import still `import core`)
  |     |-- parse (IMPORTERS registry)
  |     |-- protocols (PROTOCOL_PROBES registry)
  |     |-- probe (classify / health / model)
  |     |-- urls (join / normalize_check_path / probe_urls)
  |     |-- export (EXPORT_FORMATS registry + sync payload build/parse)
  |     +-- webdav (zero-dep WebDAV client: test / upload / download)
  |
  +--> db.py
  |     +-- SQLite data access + config.json atomic write
  |
  +--> services/  (key / task / settings / restart / sync orchestration)
  |
  +--> monitor.py
        +-- background scheduled checks
```

## 模块职责

### `app.py`

本地 Web 服务入口。负责静态资源返回、JSON API、请求参数校验、同步单条检测和后台批量检测调度。

### `core/` package

核心业务逻辑（纯函数，无 DB）。对外仍 `import core`。负责：

- 从粘贴文本 / JSON 备份解析候选 `base_url` 和 `api_key`（`parse` + `IMPORTERS`）。
- 通过 `PROTOCOL_PROBES` 注册表做协议探测与模型检查（OpenAI / Anthropic）。
- 通过 `EXPORT_FORMATS` 注册表导出 Claude Code / Codex / `.env` / PowerShell / JSON。
- `normalize_check_path` / `probe_urls`：可选相对路径覆盖 classify/health 默认入口。
- 扩展协议或导出格式时优先登记册，而不是堆进单一大文件。

### `db.py`

SQLite 存储层。每次调用独立连接，避免跨线程共享连接。负责 settings 和 keys 表的 CRUD。页面改设置时原子写入 `config.json`（先写临时文件再 `os.replace`）。

### `monitor.py`

后台定时调度。按全局配置和单条 key 状态计算到期任务，并发执行轻量探活。

### `static/`

原生 HTML/CSS/JavaScript 前端（ES Modules）。`static/app.js` 为薄编排层；业务拆到 `static/js/`：

| 模块 | 职责（摘要） |
| --- | --- |
| `state.js` / `api.js` / `utils.js` | 状态、请求、工具 |
| `cards.js` / `list_ui.js` / `list_actions.js` | 卡片渲染、列表 UI、批量操作 |
| `import.js` / `add.js` / `editor.js` | 导入、添加、编辑 |
| `export_ui.js` / `settings.js` / `tasks.js` / `dialogs.js` | 导出、设置、任务进度、对话框 |

## 数据模型

### `keys`

| 字段 | 说明 |
| --- | --- |
| `id` | 自增主键 |
| `name` | 显示名称 |
| `base_url` | API 服务地址 |
| `api_key` | API Key（库内明文；列表 API 脱敏） |
| `supports_anthropic` | 是否支持 Anthropic 协议 |
| `supports_openai` | 是否支持 OpenAI 协议 |
| `models` | 模型列表 JSON |
| `status` | `unknown` / `up` / `down` / `auth_error` |
| `latency_ms` | 最近检测延迟 |
| `last_check_at` | 最近检测时间戳 |
| `last_error` | 最近错误（`up` 时由探测逻辑清空/不展示残留） |
| `monitor_enabled` | 是否启用单条监测 |
| `interval_sec` | 单条自定义检测间隔 |
| `notes` | 备注 |
| `created_at` | 创建时间戳 |
| `check_model` | 可选：模型探测用的模型名 |
| `model_status` | 模型探测状态 |
| `model_latency_ms` | 模型探测延迟 |
| `model_last_check_at` | 模型探测时间 |
| `model_last_error` | 模型探测错误 |
| `sort_order` | 拖拽排序 |
| `check_path` | 可选：相对路径，覆盖 classify/health 默认入口；空则用内置候选 |

### `settings`

| 键 | 说明 |
| --- | --- |
| `server_host` / `server_port` | 监听地址与端口 |
| `global_monitor_enabled` | 是否启用全局监测 |
| `global_interval_sec` | 正常 key 检测间隔 |
| `down_recheck_interval_sec` | 离线 key 复检间隔 |
| `concurrency` | 后台检测并发数 |
| `request_timeout_sec` | 请求超时时间（默认 45s） |
| `auto_classify_on_add` | 新增后是否自动判别 |
| `ui_refresh_interval_sec` | 前端列表轮询间隔（`0` 关闭；默认 **15** 秒） |

## 状态判定

- `up`：接口可达，且模型接口或 Anthropic 消息接口能确认可用。聚合错误时只保留与最终状态一致的协议错误，避免其它协议 404 残留。
- `auth_error`：接口存在，但 key 被 401/403 拒绝。
- `down`：地址不可达、超时、DNS 失败或未能确认协议入口。
- `unknown`：尚未检测或刚入库。

> Anthropic 能力探针为**真实 `/messages` 生成**：慢/推理型网关一次生成可达 5–37s 且偶发 502，旧的默认 `request_timeout_sec=15s` 会让可用端点在生成完成前超时、被误判为「不支持」。现默认 **45s**，并对瞬时失败（5xx / 超时 / 连接错误）**最多重试 2 次**（任一次 200 即确认能力）。OpenAI 探针用 `GET /models`，轻量可靠，不重试。

## 错误处理

- API 返回 JSON 错误对象，格式为 `{"error":"..."}`。
- 前端对失败请求展示 toast，不静默吞错。
- 后台监测单条失败不会中断整个调度 tick。
- 单条 key 的错误信息截断保存，避免数据库记录过长。

## 自定义探活路径（`check_path`）

- 存相对路径（如 `v1/models`），禁止绝对 URL 与协议头。
- classify / health 通过 `probe_urls()` 优先使用该路径；未设置时使用各协议默认候选。
- 模型探测（chat/messages）**不**使用 `check_path`，仍走内置路径。
- 导入、JSON 导出/备份与编辑页均可读写该字段。

## 协议探测策略

- **手动检测 / 入库判别（`classify`）**：始终聚合全部已注册协议，可重新发现能力并更新 `supports_*`。
- **Anthropic 能力探针重试**：`POST /messages` 为真实生成，对瞬时失败（5xx / 超时 / 连接错误）最多重试 2 次（共 3 次），任一次 200 即确认能力；确定性结果（200 / 4xx / 401 / 403 / 404）立即返回不重试。OpenAI 探针（`GET /models`）不重试。
- **定时监测（`health_check`）**：
  - 始终探测全部已注册协议，使面板能够发现新增能力并清除已经失效的历史能力；
  - 只有本次探测状态为 `up` 的协议才写入 `supports_*`；401/403、限流、异常与超时均不确认为协议能力；
  - **不**执行 `model_check`（即使配置了 `check_model`）；模型状态仅由 classify / 手动「模型检测」更新。
  - 调度：tick 周期约 10s；存在 in-flight 批检时跳过新 tick；每 tick 最多处理 `concurrency×2` 条 due（最久未检优先），其余留待后续 tick，避免扎堆。
- **列表 revision**：写路径递增进程内 generation，并结合 `MAX(last_check_at)` 等 DB 戳生成不透明 `revision`；`GET /api/keys/revision` 供前端 silent 轮询短路。
- 修改 `base_url` / `api_key` 时库会清零能力标志，下次检测回到全量路径。

## 云同步（WebDAV）

对标 cc-switch 的「文件中枢 + 显式上传下载」，**不做静默双向实时同步**。真相源是**可移植 JSON 信封**（而非直接推 `data.db`），与「备份全部」字段对齐。

### 模块落点

| 模块 | 职责 |
| --- | --- |
| `core/webdav.py` | 纯 WebDAV 客户端（`urllib`）：`build_url` / `test_connection` / `upload` / `download`；Basic Auth，错误脱敏；无 DB 依赖 |
| `core/export.py` | `build_sync_payload` / `dumps_sync_payload` / `parse_sync_payload`：信封构造与兼容解析（信封 / 裸数组 / 单对象） |
| `services/sync_service.py` | 编排：读凭据 → 组载荷 → 调 `core.webdav` → 合并/替换入库；记录上次同步；替换前本地快照 |
| `api/router.py` | `/api/sync/{config,status,test,upload,download}`；`WebDAVError → ApiError` 映射（配置/认证→400，上游→502） |
| `static/js/sync.js` | 设置弹窗：测试 / 保存 / 上传 / 下载合并 / 下载替换（二次确认） |

### 同步载荷

```jsonc
{ "app": "apikey-monitor", "schema": 1, "exported_at": 1737000000,
  "keys": [ { "name": "", "base_url": "", "api_key": "", "check_model": "", "check_path": "" } ] }
```

下载解析时 `base_url` 经 `normalize_base_url` 规范化，`check_path` 经 `normalize_check_path`（非法则清空而非丢条目），保证跨端 `(base_url, api_key)` 去重稳定。**端口 / 监听地址等本机设置不参与同步。**

### 冲突策略

| 操作 | 行为 |
| --- | --- |
| 上传 | 本机库 → JSON 信封 → PUT 覆盖远程同路径文件（先显示远程时间） |
| 下载合并 | 复用 `db.add_keys_batch`，按 `(base_url, api_key)` 去重跳过（非破坏） |
| 下载替换 | 先 `core.export_batch` 写 `.runtime/backups/sync-replace-<ts>.json` 快照 → 删全部 → 重导；UI 需二次确认 |

### 凭据与安全

- WebDAV 应用密码以 `_webdav_password` 存于 settings 表：`_` 前缀使 `write_config_atomic` **不写入 `config.json`**，且 `SettingsService.get()` 对 API **掩码**（只回 `has_password`）。
- 远程路径规范化：禁止 `..`、绝对 URL、query/fragment、服务端 URL 内含账号密码；错误信息经 `_redact` 去掉 `user:pass@`。
- 优先 HTTPS；HTTP 时 UI 给出明文传输风险提示。
- 共享账号即共享全部 Key；文档建议使用可吊销的应用密码。

### 已知边界（MVP）

- 下载入库条目初始为 `unknown`，由定时监测在下个周期检测（不在同步请求内同步触发 classify，避免长阻塞）。
- 替换操作在事务内删 + 插；极端情况下与在途探活竞态时，探活写入已删除 id 为 no-op，可接受。
- 不加密云端 JSON（HTTPS + 应用密码 + 警告即可）；端到端加密为 Phase 2 可选项。

## 单实例启动

- 启动前读取 `.runtime/server.pid`（目录可由 `APIKEYCONFIG_RUNTIME_DIR` 覆盖）。
- 若记录的 pid 仍存活：先终止旧进程，等待端口释放，再启动。
- bind 成功后写入当前 pid；进程退出时尽力删除 pid 文件。
- 端口被**非本实例**占用时直接失败并提示，不误杀其它程序。


### 效率与体验（已实现 / 后续）

**已实现（立即项）**：监测与模型解耦、revision 短轮询、tick 防重叠与 due 上限、默认 UI 刷新 15s。

**后续（中期，未做）**：
1. 列表投影字段：轮询用瘦 payload（不含完整 `models[]`/`notes`），详情按需加载
2. 前端局部 DOM 更新：revision 变化时按 id 补丁卡片，避免整表 `innerHTML`
3. SQL 侧 due 过滤（减少 `SELECT *` 全表扫描）
4. 问题态复检策略：`auth_error` 熔断/拉长、`rate_limited`/`degraded` 独立间隔
5. 监测完成轻推：SSE 或短生命周期事件通知 UI 立即 silent load（可进一步降低固定轮询）

## 后续迭代

### 已在 v0.1.x 落地（不再作为「下一步」）

- 编辑管理：名称、地址、Key、备注、单条监控间隔、`check_model` / `check_path`
- 粘贴导入去重与跳过数量反馈
- 多格式导出：Claude Code / Codex / PowerShell / `.env` / JSON（含 `check_model` / `check_path`）
- JSON 备份与恢复
- 跨平台启动：`start.vbs`（Windows）、`start.sh`（macOS/Linux）
- 非本机绑定（`0.0.0.0`）风险提示与保存确认
- 产品定位与安全边界文档（本机单用户、无 Web 访问密码）
- `core/` 包与扩展注册表；前端 `static/js/*` 模块拆分

### 明确不做（路线图外）

- Web 访问密码 / 登录态 / 公网鉴权
- 多用户与细粒度权限模型

### 可选增强（有明确痛点再做，非承诺）

1. 可选的密钥落盘加密（迁移与口令保管成本较高）
2. 监测历史曲线 / 告警通知
3. 导入导出与监测体验的小改进（按实际使用反馈）
4. 第三协议端到端（候选如 Google Gemini）：需先选型，见 backlog 任务 `third-protocol-e2e`
5. **多机数据共享 / 坚果云 WebDAV 同步**（对标 cc-switch；JSON 信封为载荷；Phase 1 已落地，见上文「云同步（WebDAV）」；后续可选加密 / 启动提示 / MKCOL 自动建目录）
