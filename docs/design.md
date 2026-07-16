# 项目设计文档

## 目标

构建一个零依赖、本地运行的 API Key 运维工具，覆盖 API Key 收集、解析、协议判别、定时连通性监测、Web 管理和配置导出。

## 非目标

- 不作为多用户 SaaS 系统。
- 不实现公网鉴权、权限模型和审计系统。
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
  +--> core.py
  |     |-- paste parser
  |     |-- protocol classifier
  |     |-- health checker
  |     +-- config exporter
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

### `core.py`

核心业务逻辑。负责：

- 从粘贴文本中解析候选 `base_url` 和 `api_key`。
- 对 OpenAI 兼容接口调用 `/v1/models` 判别能力和模型列表。
- 对 Anthropic 兼容接口调用 `/v1/messages` 做低成本探测。
- 为 Claude Code 和 Codex CLI 生成环境变量片段。

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

优先级从高到低：

1. 完善编辑管理：名称、地址、key、备注、单条监测间隔。
2. 增加导入去重反馈，展示跳过数量。
3. 支持导出更多格式，例如 PowerShell、JSON、`.env`。
4. 增加数据库备份与恢复。
5. 增加可选的本地访问密码。

