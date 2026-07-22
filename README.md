# API Key 配置与监测面板

[![Release](https://img.shields.io/github/v/release/BeHappyWsz/apikey-monitor?display_name=tag)](https://github.com/BeHappyWsz/apikey-monitor/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **管理员访问**：首次启动会创建管理员账户。登录、初始密码修改、会话保护、CSRF 防护和用户管理说明见 [`docs/authentication.md`](docs/authentication.md)。

本地运行的 **API Key 管理小工具**：收集 / 解析 / 检测 / 导出 OpenAI 兼容与 Anthropic 兼容接口配置。

> **运行依赖**：Python 3.10+、`argon2-cffi`、`PyMySQL` 与 `redis`（见 `requirements.txt`）以及现代浏览器。默认只监听本机 `127.0.0.1`。

## 功能一览

- **粘贴导入**：从环境变量、curl、纯文本解析 `base_url` + `api_key`；预览可改名称/URL/Key；结果展示新增 / 跳过重复 / 无效
- **手动添加**：单条填写，可选保存后立即检测
- **协议判别**：自动识别 OpenAI / Anthropic 能力
- **自定义探活路径**：每条 Key 可选相对路径 `check_path`，覆盖连通性/协议探测默认入口（模型探测仍用内置路径）
- **定时监测**：连通性、认证状态、延迟；支持全局与单条开关
- **Web 管理**：筛选、批量检测/删除、拖拽排序、编辑、导出
- **管理员登录与用户管理**：管理员会话、首次登录强制修改初始密码、创建账户，以及启用/禁用其他管理员账户（禁用会立即撤销其会话）
- **批量任务**：导入/批量检测显示进度与失败数
- **配置导出**：Claude / Codex（对齐 **CC Switch** 深链与粘贴 JSON）、`.env`、PowerShell、JSON；支持**批量 JSON**、下载文件与格式记忆；卡片可一键「导入CCSwitch」
- **体验优化**：工具栏「更多」菜单、无选中禁用批量操作、`Ctrl+Enter` 快捷保存、批量检测汇总与问题项筛选
- **列表脱敏**：列表/详情不返回明文 Key；卡片可一键复制完整 Key（按需取 secret）
- **JSON 备份/恢复**：备份全部为 JSON；粘贴导入可直接识别同格式 JSON
- **可选云同步（WebDAV）**：对接坚果云等 WebDAV，显式上传 / 下载合并 / 下载替换（替换前自动本地备份）；不额外引入 WebDAV 客户端依赖
- **安全换端口**：先释放旧端口再启新端口，失败自动回滚
- **跨平台启动**：Windows `start.vbs`；macOS/Linux `start.sh`（可选后台）

## 环境要求

| 项目 | 要求 |
|------|------|
| Python | **3.10+**（推荐 3.11 / 3.12 / 3.13） |
| Python 包 | `argon2-cffi==25.1.0`、`PyMySQL==1.1.2`、`redis==7.1.0`（由 `requirements.txt` 固定） |
| 浏览器 | 支持 ES Modules 的现代浏览器 |
| 系统 | Windows / macOS / Linux（Windows：`start.vbs`；macOS/Linux：`start.sh`） |

## 快速启动

```bash
# 进入项目目录后
python -m pip install -r requirements.txt
python app.py
```

默认打开：

```text
http://127.0.0.1:7878
```

常用参数：

```bash
python app.py --host 127.0.0.1 --port 7878
python app.py --no-browser
```

### Windows 静默启动

双击项目根目录的 `start.vbs`：无 CMD 窗口后台启动（优先 `pythonw.exe`，失败回退 `python.exe`），并加 `--no-browser`。需自行在浏览器打开上述地址。

### macOS / Linux 启动脚本

```bash
chmod +x start.sh   # 首次
./start.sh          # 前台，--no-browser
./start.sh --bg     # 后台（nohup）
./start.sh --host 127.0.0.1 --port 7878
```

脚本会切换到仓库根目录，优先使用 `python3`，否则 `python`。额外参数会传给 `app.py`。

定时监测仅做连通性探活（不附带模型探测）。调度使用数据库索引读取到期 Key，后台、手动与批量检测共用设置中的并发上限；`auth_error`、限流与网关异常会自动降低复检频率，避免无效请求持续消耗上游配额。前端 silent 刷新通过 `GET /api/keys/revision` 短路无变化请求。

重复启动时，`app.py` 会读取 `.runtime/server.pid`：若检测到本工具旧实例仍在运行，会先关闭再启动，减少端口残留。

### 端口与监听

- 默认 **仅绑定 `127.0.0.1`**，适合本机运维，**不要直接暴露公网**。
- 可在页面右上角「系统设置」修改 host/port；保存后可选择安全重启（释放旧端口 → 起新端口，失败回滚）。
- 启动时显式传入 `--host` / `--port` 时，命令行优先于页面配置。

## 使用流程

1. 打开页面 →「粘贴导入」或「手动添加」
2. 粘贴含 `base_url` / `api_key` 的文本 →「解析预览」→ 确认 →「批量入库」
3. 在列表查看状态、延迟、协议与模型检测结果
4. 需要使用时点「导入CCSwitch」一键打开，或「导出」复制 Claude / Codex 粘贴配置 / `.env` / JSON 等

粘贴导入可混入普通说明或聊天内容：会识别环境变量、`curl`、同一行的 `URL + Key`、`Bearer` 头，以及 Markdown ````json` 代码块中的备份；只有近邻可关联的 URL 和密钥才会生成候选，降低误把对话链接或长文本当作 Key 的风险。

## 支持的粘贴格式

```text
ANTHROPIC_BASE_URL=https://api.example.com
ANTHROPIC_AUTH_TOKEN=sk-xxxx
```

```text
OPENAI_BASE_URL=https://api.example.com/v1
OPENAI_API_KEY=sk-xxxx
```

```text
https://api.example.com sk-xxxx
```

解析会自动剥离常见路径后缀，如 `/v1/models`、`/v1/chat/completions`、`/v1/messages`。

## 导出说明

| 格式 | 用途 |
|------|------|
| Claude · CCSwitch | `{"env":{ANTHROPIC_*}}` JSON；endpoint = `base + /anthropic`；可一键深链导入 CC Switch |
| Codex · CCSwitch | `{"auth","config"}` JSON（config 为 TOML）；endpoint = `base + /v1`；可一键深链导入 |
| `.env` / PowerShell | 本地脚本环境变量 |
| JSON | 单条或**批量**；字段 `name` / `base_url` / `api_key` / `check_model` / `check_path` |

- 卡片 **「导入CCSwitch」**：按协议能力 / 严格验证适配器自动选 Claude/Codex，打开 `ccswitch://` 深链；无法判定时弹出二选一。本机需已安装 [CC Switch](https://github.com/farion1231/cc-switch) 并注册协议。
- **有 `check_model`** 时：写入 model，供应商展示名追加为 `名称 · 模型`（便于在 CC Switch 中区分同网关多模型）；**无 model 时整段省略**。
- 深链为单向唤起，**无导入成功回调**；CC Switch 未响应时可在导出弹窗复制粘贴配置或复制深链。
- 导出、复制与深链均含**完整 API Key**，注意屏幕共享、日志与勿外传深链。

## 定时监测

设置中可调：

- 监听地址和端口
- 全局监测开关
- 列表自动刷新间隔（默认见 `config.json`，常见为 5–10 秒；`0`=关闭）
- 正常间隔 / 离线复检间隔
- 并发数、请求超时

异常状态会在上述基础上自动退避：`degraded` 至少 10 分钟，`rate_limited` 至少 15 分钟，`auth_error` 至少 6 小时；每条 Key 会加约 ±5% 的确定性抖动，避免大量 Key 同秒发起请求。手动检测不受等待时间影响，但仍共享同一个并发上限。

每条 Key 也可单独开/关监测。

## 登录与用户管理

- 首次启动且数据库中没有账户时，程序使用 `config.json` 中的
  `_bootstrap_admin_username` 和 `_bootstrap_admin_password` 创建首个管理员；初始密码至少 12 位，首次登录后必须修改。
- 所有账户都是管理员。已登录管理员可在右上角“用户管理”中创建账户，或启用/禁用其他账户；不能禁用当前登录账户。
- 登录会话为 HttpOnly Cookie，写操作需要 CSRF 令牌；会话默认 8 小时过期，退出或禁用账户会撤销对应会话。
- 默认仍只监听 `127.0.0.1`。如需经 HTTPS 反向代理对外提供访问，请按 [`docs/authentication.md`](docs/authentication.md) 配置可信代理与 `APIKEYCONFIG_TRUST_PROXY=1`。

## 数据与目录

| 路径 | 说明 |
|------|------|
| `data.db` | SQLite，**首次启动自动创建，勿提交到 Git**（含 WebDAV 应用密码） |
| `config.json` | 首次初始化的设置种子和私有启动配置；运行时设置以 DB 为准，程序不会回写该文件。不要向被 Git 跟踪的文件写入真实密码；部署时优先使用环境变量或仓库外的配置路径。 |
| `.runtime/` | 单实例 pid / 重启状态；`backups/` 存放云同步「替换前」本地快照（`APIKEYCONFIG_RUNTIME_DIR` 覆盖） |
| `app.py` | 入口与 HTTP 生命周期 |
| `core/` | 解析、探活、导出、WebDAV 客户端（包结构 + 扩展注册表；`import core` 仍可用） |
| `db.py` | SQLite / 配置 |
| `api/` | 路由与校验 |
| `services/` | Key / 任务 / 设置 / 重启 / 云同步 |
| `monitor.py` | 定时调度 |
| `static/` | 前端（原生 HTML/CSS/ESM；`app.js` + `js/*` 模块） |
| `docs/` | API / 设计说明 |
| `tests/` | 单元与集成测试 |
| `start.vbs` | Windows 静默启动 |
| `start.sh` | macOS / Linux 启动（`--no-browser`，可选 `--bg`） |
| `LICENSE` | MIT |

## 安全注意

- **定位**：本地管理员运维工具。默认绑定 `127.0.0.1`；提供管理员登录，但仍不应作为未受 HTTPS 反向代理保护的公网服务。
- API Key **明文**存在本地 `data.db`，请保护目录与系统账户权限；不要把 `data.db` 同步到不可信位置。
- **不建议**监听 `0.0.0.0`，更不要暴露公网。页面「系统设置」在选择 `0.0.0.0` 时会显示风险提示并二次确认。
- **列表脱敏**：`GET /api/keys`、`GET /api/keys/{id}` 仅返回 `api_key_masked` / `has_api_key`。
- 完整密钥仅通过：编辑页复制/显示、导出、`GET /api/keys/{id}/secret`。
- 编辑时 API Key **留空 = 不修改**已有密钥。

## 备份与恢复

1. 工具栏 **「备份全部」** → 复制/保存 JSON（含全部 Key 明文，请妥善保管）。
2. 新环境打开 **「粘贴导入」** 或空状态 **「从 JSON 恢复」**，粘贴备份 → 解析预览 → 入库。
3. 也可导出选中项为 JSON，再同样方式导入。

## 云同步（WebDAV / 坚果云）

页头「☁ 云同步」可把**可移植 JSON**（名称 / Base URL / Key / 检测模型 / 检测路径）显式上传到 WebDAV，或在另一台机器下载合并 / 替换。它只读写 `tbl_keys` 中的这些可移植字段：监听/监测设置、用户与会话、密钥状态和 WebDAV 凭据都不参与同步。所有操作均为手动触发，**不会静默双向同步**。

**坚果云配置示例：**

| 项 | 值 |
|----|-----|
| 服务器 | `https://dav.jianguoyun.com/dav/` |
| 用户名 | 登录邮箱 |
| 密码 | 账号设置中的 **应用密码**（非登录密码） |
| 远程路径 | `/apikey-monitor/backup.json` |

**操作：**

- **测试连接**：探测远程文件是否存在及更新时间（PROPFIND，失败回退 HEAD）。
- **上传到云端**：以本机当前库生成 JSON 信封覆盖远程同路径文件。
- **下载合并**：按 `base_url + api_key` 去重，跳过已存在的条目（非破坏）。
- **下载替换**：以云端为准覆盖本机（**替换前自动在 `.runtime/backups/` 存一份本地备份**，需二次确认）。

> 安全提示：共享坚果云账号即共享全部 Key；建议使用可吊销的**应用密码**；优先 HTTPS。下载的条目初始为「未知」状态，定时监测会在下个周期自动检测。同一云端文件同时只允许一台设备写入。

## 开发与测试

```bash
# Python 测试
python -m unittest discover -s tests -v

# 前端语法检查（需 Node.js）
node --check static/app.js
node --check static/js/cards.js
node --check static/js/list_ui.js
node --check static/js/export_ui.js
node --check static/js/editor.js
node --check static/js/state.js
node --check static/js/sync.js

# 可选 state 单测
node --test tests/state.test.mjs
```

更细的接口说明见 [`docs/api.md`](docs/api.md)。

## 许可证

本项目以 [MIT License](LICENSE) 开源。欢迎阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 参与贡献；变更见 [CHANGELOG.md](CHANGELOG.md)。

---

**仓库维护提示**：首次发布前请确认工作区无 `data.db`、真实密钥与本地 `Review/` 草稿；绑定远程与 `git push` 可在准备好后再做。
