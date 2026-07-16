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
  |     +-- export (EXPORT_FORMATS registry)
  |
  +--> db.py
  |     +-- SQLite data access
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
- 扩展协议或导出格式时优先登记册，而不是堆进单一大文件。

### `db.py`

SQLite 存储层。每次调用独立连接，避免跨线程共享连接。负责 settings 和 keys 表的 CRUD。

### `monitor.py`

后台定时调度。按全局配置和单条 key 状态计算到期任务，并发执行轻量探活。

### `static/`

原生 HTML/CSS/JavaScript 前端。负责列表管理、粘贴导入、设置、导出、批量操作和状态刷新。

## 数据模型

### `keys`

| 字段 | 说明 |
| --- | --- |
| `id` | 自增主键 |
| `name` | 显示名称 |
| `base_url` | API 服务地址 |
| `api_key` | API Key |
| `supports_anthropic` | 是否支持 Anthropic 协议 |
| `supports_openai` | 是否支持 OpenAI 协议 |
| `models` | 模型列表 JSON |
| `status` | `unknown` / `up` / `down` / `auth_error` |
| `latency_ms` | 最近检测延迟 |
| `last_check_at` | 最近检测时间戳 |
| `last_error` | 最近错误 |
| `monitor_enabled` | 是否启用单条监测 |
| `interval_sec` | 单条自定义检测间隔 |
| `notes` | 备注 |
| `created_at` | 创建时间戳 |

### `settings`

| 键 | 说明 |
| --- | --- |
| `global_monitor_enabled` | 是否启用全局监测 |
| `global_interval_sec` | 正常 key 检测间隔 |
| `down_recheck_interval_sec` | 离线 key 复检间隔 |
| `concurrency` | 后台检测并发数 |
| `request_timeout_sec` | 请求超时时间 |
| `auto_classify_on_add` | 新增后是否自动判别 |

## 状态判定

- `up`：接口可达，且模型接口或 Anthropic 消息接口能确认可用。
- `auth_error`：接口存在，但 key 被 401/403 拒绝。
- `down`：地址不可达、超时、DNS 失败或未能确认协议入口。
- `unknown`：尚未检测或刚入库。

## 错误处理

- API 返回 JSON 错误对象，格式为 `{"error":"..."}`。
- 前端对失败请求展示 toast，不静默吞错。
- 后台监测单条失败不会中断整个调度 tick。
- 单条 key 的错误信息截断保存，避免数据库记录过长。

## 后续迭代

### 已在 v0.1.x 落地（不再作为「下一步」）

- 编辑管理：名称、地址、Key、备注、单条监控间隔
- 粘贴导入去重与跳过数量反馈
- 多格式导出：Claude Code / Codex / PowerShell / `.env` / JSON
- JSON 备份与恢复
- 跨平台启动：`start.vbs`（Windows）、`start.sh`（macOS/Linux）
- 非本机绑定（`0.0.0.0`）风险提示与保存确认
- 产品定位与安全边界文档（本机单用户、无 Web 访问密码）

### 明确不做（路线图外）

- Web 访问密码 / 登录态 / 公网鉴权
- 多用户与细粒度权限模型

### 可选增强（有明确痛点再做，非承诺）

1. 可选的密钥落盘加密（迁移与口令保管成本较高）
2. 监测历史曲线 / 告警通知
3. 导入导出与监测体验的小改进（按实际使用反馈）


### Per-key custom check path

Optional check_path stores a relative path used by classify/health protocol probes instead of default candidate_urls endpoints. Validated relative-only via core.normalize_check_path. Model checks keep default chat/messages URLs.
