# API Key 配置与监测面板

[![Release](https://img.shields.io/github/v/release/BeHappyWsz/apikey-monitor?display_name=tag)](https://github.com/BeHappyWsz/apikey-monitor/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

本地运行的 **API Key 管理小工具**：收集 / 解析 / 检测 / 导出 OpenAI 兼容与 Anthropic 兼容接口配置。

> **零第三方依赖**：仅需 Python 标准库 + 现代浏览器。默认只监听本机 `127.0.0.1`。

## 功能一览

- **粘贴导入**：从环境变量、curl、纯文本解析 `base_url` + `api_key`；预览可改名称/URL/Key；结果展示新增 / 跳过重复 / 无效
- **手动添加**：单条填写，可选保存后立即检测
- **协议判别**：自动识别 OpenAI / Anthropic 能力
- **定时监测**：连通性、认证状态、延迟；支持全局与单条开关
- **Web 管理**：筛选、批量检测/删除、拖拽排序、编辑、导出
- **批量任务**：导入/批量检测显示进度与失败数
- **配置导出**：Claude Code、Codex CLI、`.env`、PowerShell、JSON；支持**批量 JSON**、下载文件与格式记忆
- **体验优化**：工具栏「更多」菜单、无选中禁用批量操作、`Ctrl+Enter` 快捷保存、批量检测汇总与问题项筛选、卡片一键 Codex/Claude
- **列表脱敏**：列表/详情不返回明文 Key；卡片可一键复制完整 Key（按需取 secret）
- **JSON 备份/恢复**：备份全部为 JSON；粘贴导入可直接识别同格式 JSON
- **安全换端口**：先释放旧端口再启新端口，失败自动回滚

## 环境要求

| 项目 | 要求 |
|------|------|
| Python | **3.10+**（推荐 3.11 / 3.12 / 3.13） |
| 依赖 | **无**（仅标准库：`http.server` / `sqlite3` / `urllib` 等） |
| 浏览器 | 支持 ES Modules 的现代浏览器 |
| 系统 | Windows / macOS / Linux（Windows：`start.vbs`；macOS/Linux：`start.sh`） |

## 快速启动

```bash
# 进入项目目录后
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

### 端口与监听

- 默认 **仅绑定 `127.0.0.1`**，适合本机运维，**不要直接暴露公网**。
- 可在页面右上角「系统设置」修改 host/port；保存后可选择安全重启（释放旧端口 → 起新端口，失败回滚）。
- 启动时显式传入 `--host` / `--port` 时，命令行优先于页面配置。

## 使用流程

1. 打开页面 →「粘贴导入」或「手动添加」
2. 粘贴含 `base_url` / `api_key` 的文本 →「解析预览」→ 确认 →「批量入库」
3. 在列表查看状态、延迟、协议与模型检测结果
4. 需要使用时点「导出」，复制 Claude Code / Codex / `.env` / JSON 等

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
| Claude Code | Anthropic 环境变量 |
| Codex CLI | OpenAI 兼容环境变量 |
| `.env` / PowerShell | 本地脚本 |
| JSON | 单条或**批量**；字段仅 `name` / `base_url` / `api_key` / `check_model` |

导出与复制会包含**完整 API Key**，注意屏幕共享与日志。

## 定时监测

设置中可调：

- 监听地址和端口
- 全局监测开关
- 列表自动刷新间隔（默认 5 秒，0=关闭）
- 正常间隔 / 离线复检间隔
- 并发数、请求超时

每条 Key 也可单独开/关监测。

## 数据与目录

| 路径 | 说明 |
|------|------|
| `data.db` | SQLite，**首次启动自动创建，勿提交到 Git** |
| `config.json` | 默认配置模板（无密钥）；页面修改会写入数据库覆盖 |
| `app.py` | 入口与 HTTP 生命周期 |
| `core/` | 解析、探活、导出 |
| `db.py` | SQLite / 配置 |
| `api/` | 路由与校验 |
| `services/` | Key / 任务 / 设置 / 重启 |
| `monitor.py` | 定时调度 |
| `static/` | 前端（原生 HTML/CSS/ESM） |
| `docs/` | API / 设计说明 |
| `tests/` | 单元与集成测试 |
| `start.vbs` | Windows 静默启动 |
| `start.sh` | macOS / Linux 启动（`--no-browser`，可选 `--bg`） |
| `LICENSE` | MIT |

## 安全注意

- **定位**：本机单用户运维工具。默认绑定 `127.0.0.1`，**不提供** Web 登录或访问密码；请勿当作可公网暴露的服务。
- API Key **明文**存在本地 `data.db`，请保护目录与系统账户权限；不要把 `data.db` 同步到不可信位置。
- **不建议**监听 `0.0.0.0`，更不要暴露公网。页面「系统设置」在选择 `0.0.0.0` 时会显示风险提示并二次确认。
- **列表脱敏**：`GET /api/keys`、`GET /api/keys/{id}` 仅返回 `api_key_masked` / `has_api_key`。
- 完整密钥仅通过：编辑页复制/显示、导出、`GET /api/keys/{id}/secret`。
- 编辑时 API Key **留空 = 不修改**已有密钥。

## 备份与恢复

1. 工具栏 **「备份全部」** → 复制/保存 JSON（含全部 Key 明文，请妥善保管）。
2. 新环境打开 **「粘贴导入」** 或空状态 **「从 JSON 恢复」**，粘贴备份 → 解析预览 → 入库。
3. 也可导出选中项为 JSON，再同样方式导入。

## 开发与测试

```bash
# Python 测试
python -m unittest discover -s tests -v

# 前端语法检查（需 Node.js）
node --check static/app.js
node --check static/js/editor.js
node --check static/js/state.js

# 可选 state 单测
node --test tests/state.test.mjs
```

更细的接口说明见 [`docs/api.md`](docs/api.md)。

## 许可证

本项目以 [MIT License](LICENSE) 开源。欢迎阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 参与贡献；变更见 [CHANGELOG.md](CHANGELOG.md)。

---

**仓库维护提示**：首次发布前请确认工作区无 `data.db`、真实密钥与本地 `Review/` 草稿；绑定远程与 `git push` 可在准备好后再做。
