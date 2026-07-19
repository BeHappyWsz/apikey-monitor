# HTTP API 文档

## Authentication

Except `GET /api/system/health`, `GET /api/auth/bootstrap`, and
`POST /api/auth/login`, API routes require the `apikeyconfig_session` HttpOnly
cookie. Unsafe requests also require `X-CSRF-Token` from `GET /api/auth/me`.

| Route | Purpose |
| --- | --- |
| `POST /api/auth/login` | Body: `username`, `password`; sets the session cookie and returns user + CSRF token. |
| `POST /api/auth/logout` | Revokes the current session; requires CSRF. |
| `GET /api/auth/me` | Returns the authenticated user and CSRF token. |
| `GET /api/auth/users` | Lists administrator accounts. |
| `POST /api/auth/users` | Creates an administrator; requires `username` and a 12+ character password. |

Authentication failures use `401 unauthenticated`, CSRF failures use
`403 csrf_failed`, and login throttling uses `429 login_rate_limited`.

服务默认地址：

```text
http://127.0.0.1:7878
```

所有业务接口使用 JSON。

## Key 管理

### 获取列表

```http
GET /api/keys
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
  "status": "up"
}
```

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

WebDAV 同步是可选能力。服务器会把当前 Key 列表打包为 JSON 同步载荷后上传到远程文件；下载时可选择合并或全量替换。`password` 仅在保存时提交，查询配置不会返回明文密码。

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
  "server_host": "127.0.0.1",
  "server_port": "7878",
  "global_monitor_enabled": "1",
  "global_interval_sec": "300",
  "down_recheck_interval_sec": "120",
  "concurrency": "8",
  "request_timeout_sec": "15",
  "auto_classify_on_add": "1",
  "ui_refresh_interval_sec": "5"
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

返回 `candidates` 数组，元素含 `name`、`base_url`、`api_key`，以及可选的 `check_model`、`check_path`、`notes`。

## 自定义探活路径 `check_path`

每条 Key 可选字段 `check_path`：相对于 `base_url` 的 URL 路径（如 `v1/models`）。

- 空字符串：使用各协议内置候选入口
- 禁止绝对 URL（`http://` / `https://` 等）
- **仅**作用于 classify / health 探活；**不**作用于模型 chat/messages 探测
- 出现在：创建/更新 Key、JSON 导入/导出/备份、编辑表单
