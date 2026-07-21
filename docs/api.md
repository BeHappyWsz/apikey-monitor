# HTTP API 文档

## Authentication

Except `GET /api/system/health`, `GET /api/auth/bootstrap`, and
`POST /api/auth/login`, API routes require the `apikeymonitor_session` HttpOnly
cookie. Unsafe requests also require `X-CSRF-Token` from `GET /api/auth/me`.

| Route | Purpose |
| --- | --- |
| `POST /api/auth/login` | Body: `username`, `password`; sets the session cookie and returns user + CSRF token. |
| `POST /api/auth/logout` | Revokes the current session; requires CSRF. |
| `GET /api/auth/me` | Returns the authenticated user and CSRF token. |
| `GET /api/auth/users` | Lists administrator accounts. |
| `POST /api/auth/users` | Creates an administrator; requires `username` and a 12+ character password. |
| `PUT /api/auth/users/{id}` | Enables or disables another administrator with `{ "enabled": true\|false }`; disabling revokes that account's sessions and self-disable is rejected. |

Authentication failures use `401 unauthenticated`, disabled accounts receive
`403 account_disabled`, CSRF failures use `403 csrf_failed`, and login
throttling uses `429 login_rate_limited`.

服务默认地址：

```text
http://127.0.0.1:7878
```

所有业务接口使用 JSON。

## Key 管理

### 获取列表

```http
GET /api/keys
GET /api/keys/page?limit=50&cursor=&status=all&q=&sort=default
GET /api/keys/revision
```

> 列表与单条详情默认脱敏：响应不含明文 `api_key`，仅含 `api_key_masked`、`has_api_key`。完整密钥见 `/secret` 或导出接口。

返回 key 数组，元素示例：

```json
{
  "id": 1,
  "name": "example",
  "base_url": "https://api.example.com",
  "api_key_masked": "sk-xx••••••xxxx",
  "has_api_key": true,
  "status": "up",
  "check_model": "gpt-4o-mini",
  "model_status": "up",
  "model_verification_version": 1,
  "model_probe_adapter": "openai_chat"
}
```

`GET /api/keys` remains available for compatibility. The web panel uses the
cursor-paged endpoint so it does not repeatedly transfer every key:

- `limit`: optional `1`–`100`, default `50` (values outside that range are
  constrained by the server).
- `cursor`: opaque value from the previous response's `next_cursor`; omit it
  for the first page. Each cursor is bound to the `sort` that produced it;
  replaying a cursor under a different `sort` returns `400 invalid_page`.
- `status`: `all`, `up`, `down`, `auth_error`, `unknown`, `issue`, or
  `problem`.
- `q`: optional case-insensitive search over the public list fields.
- `sort`: `default` (user-defined `sort_order`, descending id as tiebreak —
  matches the pre-existing behaviour), `created_desc` (most-recently imported
  first), or `created_asc` (oldest first). When `sort` is not `default`,
  the manual drag-to-reorder UI is disabled because the server-side
  `ORDER BY` ignores `sort_order`. Unknown values respond with
  `400 invalid_page`.

The response is always masked and has this shape:

```json
{
  "items": [{ "id": 1, "name": "example", "api_key_masked": "sk-…" }],
  "next_cursor": "WzAsLTEwLDFd",
  "total": 148,
  "summary": {
    "all": 148,
    "up": 120,
    "down": 4,
    "auth_error": 2,
    "unknown": 20,
    "issue": 2,
    "problem": 28,
    "avg_latency_ms": 231
  },
  "revision": "opaque-revision"
}
```

`total` is scoped to the requested `status` and `q`; `summary` is scoped to
`q` only, so the panel can keep status counters accurate. A changed list
revision only raises a refresh prompt while the user is browsing; pressing
Refresh explicitly reloads the first page with the current filters.

`model_probe_adapter` is non-secret metadata from strict model verification.
Values are `openai_chat`, `openai_responses`, `anthropic_messages`, or empty
when no usable adapter has been confirmed. The web panel uses it to show
ccswitch access guidance; portable JSON export intentionally excludes it.

### 新增单条

```http
POST /api/keys
Content-Type: application/json
```

```json
{
  "name": "example",
  "base_url": "https://api.example.com",
  "api_key": "sk-xxxx",
  "monitor_enabled": 1,
  "interval_sec": null,
  "notes": ""
}
```

新增后会同步执行一次协议判别。

### 批量新增

```http
POST /api/keys/batch
Content-Type: application/json
```

```json
{
  "items": [
    {
      "name": "example",
      "base_url": "https://api.example.com",
      "api_key": "sk-xxxx"
    }
  ]
}
```

返回新增 id 列表，并在后台执行判别。无效候选会被跳过。

```json
{
  "ids": [1],
  "count": 1,
  "skipped_invalid": 0,
  "skipped_duplicate": 0
}
```

### 更新单条

```http
PUT /api/keys/{id}
Content-Type: application/json
```

支持字段（`api_key` 可省略或传空字符串，表示不修改已有密钥）：

```json
{
  "name": "new name",
  "base_url": "https://api.example.com",
  "api_key": "sk-xxxx",
  "monitor_enabled": 1,
  "interval_sec": 300,
  "notes": "memo"
}
```

### 删除单条

```http
DELETE /api/keys/{id}
```

### 批量删除

```http
POST /api/keys/batch_delete
Content-Type: application/json
```

```json
{
  "ids": [1, 2, 3]
}
```

### 单条检测

```http
POST /api/keys/{id}/check
```

### 批量检测

```http
POST /api/keys/batch_check
Content-Type: application/json
```

```json
{
  "ids": [1, 2, 3]
}
```

## 导入解析

### 解析粘贴文本

```http
POST /api/import/parse
Content-Type: application/json
```

```json
{
  "text": "OPENAI_BASE_URL=https://api.example.com\nOPENAI_API_KEY=sk-xxxx"
}
```

返回：

```json
{
  "candidates": [
    {
      "base_url": "https://api.example.com",
      "api_key": "sk-xxxx",
      "name": ""
    }
  ]
}
```

## 配置导出

### 获取完整 API Key（按需）

```http
GET /api/keys/{id}/secret
```

仅在复制 / 显示密钥时调用。响应示例：

```json
{
  "id": 1,
  "api_key": "sk-xxxx",
  "api_key_masked": "sk-xx••••••xxxx"
}
```

### 单条导出

```http
GET /api/keys/{id}/export?fmt=claude
GET /api/keys/{id}/export?fmt=codex
GET /api/keys/{id}/export?fmt=env
GET /api/keys/{id}/export?fmt=powershell
GET /api/keys/{id}/export?fmt=json
```

返回：

```json
{
  "text": "export OPENAI_BASE_URL=..."
}
```

单条导出 `fmt` 支持：`claude`、`codex`、`env`、`powershell`、`json`。

### 批量导出 JSON

```http
POST /api/keys/batch_export
Content-Type: application/json
```

```json
{
  "ids": [1, 2, 3],
  "fmt": "json"
}
```

返回：

```json
{
  "text": "[{...}]",
  "count": 3,
  "fmt": "json"
}
```

## WebDAV 同步

WebDAV 同步是可选能力。服务器会把当前 Key 列表打包为 JSON 同步载荷后上传到远程文件；下载时可选择合并或全量替换。同步边界固定为 `name`、`base_url`、`api_key`、`check_model`、`check_path`：替换模式也只会替换本机 `tbl_keys` 记录，绝不会覆盖设置、用户、会话、WebDAV 凭据、监测状态或其他本机数据。`password` 仅在保存时提交，查询配置不会返回明文密码。

### 获取同步配置

```http
GET /api/sync/config
```

响应示例：

```json
{
  "configured": true,
  "server": "https://dav.jianguoyun.com/dav/",
  "username": "me@example.com",
  "remote_path": "apikey-monitor/backup.json",
  "has_password": true
}
```

### 保存同步配置

```http
POST /api/sync/config
Content-Type: application/json
```

```json
{
  "server": "https://dav.jianguoyun.com/dav/",
  "username": "me@example.com",
  "password": "应用密码",
  "remote_path": "apikey-monitor"
}
```

`remote_path` 可填写目录或 JSON 文件。目录会自动保存为该目录下的 `backup.json`，例如 `apikey-monitor` 会规范化为 `apikey-monitor/backup.json`。再次保存时 `password` 传空字符串表示保留原密码。

### 测试连接

```http
POST /api/sync/test
```

响应示例：

```json
{
  "ok": true,
  "exists": false,
  "last_modified": null
}
```

### 上传到 WebDAV

```http
POST /api/sync/upload
```

响应示例：

```json
{
  "count": 3,
  "remote_modified": "Wed, 17 Jul 2026 10:00:00 GMT"
}
```

### 从 WebDAV 下载

```http
POST /api/sync/download
Content-Type: application/json
```

```json
{
  "mode": "merge"
}
```

`mode` 支持：

- `merge`：合并导入，跳过重复项。
- `replace`：全量替换本机 Key，替换前会尽量写入本地 JSON 快照。

响应示例：

```json
{
  "count": 2,
  "skipped_duplicate": 1,
  "mode": "merge",
  "backup_path": null,
  "remote_modified": "Wed, 17 Jul 2026 10:00:00 GMT"
}
```

### 获取同步状态

```http
GET /api/sync/status
```

```json
{
  "last_sync": "upload|count=3|skipped=0|ts=1784282400"
}
```

## 设置

### 获取设置

```http
GET /api/settings
```

### 保存设置

```http
POST /api/settings
Content-Type: application/json
```

```json
{
  "serverHost": "127.0.0.1",
  "serverPort": "7878",
  "globalMonitorEnabled": "1",
  "globalIntervalSec": "300",
  "downRecheckIntervalSec": "120",
  "concurrency": "8",
  "requestTimeoutSec": "45",
  "autoClassifyOnAdd": "1",
  "uiRefreshIntervalSec": "5"
}
```

## 系统操作

### 健康检查

```http
GET /api/system/health
```

```json
{
  "status": "ok",
  "pid": 12345,
  "host": "127.0.0.1",
  "port": 7878
}
```

### 安全重启服务

```http
POST /api/system/restart
Content-Type: application/json
```

接口返回 `202` 和重启任务。服务随后停止监测线程与旧 HTTP Server，确认旧端口已释放后启动目标端口；目标服务启动或健康检查失败时，自动恢复旧设置并重新启动旧端口。

```json
{
  "restart_id": "a1b2c3d4e5f6",
  "status": "validating",
  "message": "目标端口校验通过",
  "old_url": "http://127.0.0.1:7878",
  "target_url": "http://127.0.0.1:8787",
  "steps": []
}
```

### 查询重启状态

```http
GET /api/system/restart/{restart_id}
```

终态包括：

- `succeeded`：新端口启动成功；
- `rolled_back`：新端口失败，旧端口已恢复；
- `failed`：新旧端口均未能启动，需要手动处理；
- `no_change`：监听地址和端口未变化。

## 后台任务

### 查询检测任务

```http
GET /api/tasks/{task_id}
```

批量检测和批量导入后的自动检测会返回任务对象，状态包括 `queued`、`running`、`completed`、`partial_failed` 和 `failed`，并包含 `total`、`completed`、`failed`、`skipped` 与最多 10 条错误摘要。


### JSON 导出字段

单条/批量 `fmt=json` 仅输出可移植配置字段：`name`、`base_url`、`api_key`、`check_model`、`check_path`（不含 `id`、状态、协议能力等内部字段）。


### 备份全部（JSON）

```http
GET /api/keys/export_all
```

返回全部 Key 的可移植 JSON 文本（字段同单条/批量 JSON 导出）：

```json
{
  "text": "[{\"name\":\"...\",\"base_url\":\"...\",\"api_key\":\"...\",\"check_model\":\"...\",\"check_path\":\"...\"}]",
  "count": 2,
  "fmt": "json"
}
```

### 导入解析（文本或 JSON）

```http
POST /api/import/parse
Content-Type: application/json
```

```json
{ "text": "...环境变量或 JSON 备份..." }
```

`text` 可为：

- 环境变量 / curl / `URL + Key` 纯文本
- 导出/备份 JSON 数组、单条对象，或 `{ "items": [...] }` / `{ "keys": [...] }`
- 含普通说明文字的 Markdown；JSON 位于 ````json` 代码块时也会被识别。

解析器只会把同一行或相邻少量行内可关联的 URL 与密钥组成候选项，避免把聊天记录中相距较远的普通链接和长字符串误当成配置。支持 `Bearer`、`OPENAI_*` / `ANTHROPIC_*`、`api_key` / `apiKey` 等常见标记；最终导入前仍由后端校验 URL 与密钥字段。

返回 `candidates` 数组，元素含 `name`、`base_url`、`api_key`，以及可选的 `check_model`、`check_path`、`notes`。

## 自定义探活路径 `check_path`

每条 Key 可选字段 `check_path`：相对于 `base_url` 的 URL 路径（如 `v1/models`）。

- 空字符串：使用各协议内置候选入口
- 禁止绝对 URL（`http://` / `https://` 等）
- **仅**作用于 classify / health 探活；**不**作用于模型 chat/messages 探测
- 出现在：创建/更新 Key、JSON 导入/导出/备份、编辑表单
