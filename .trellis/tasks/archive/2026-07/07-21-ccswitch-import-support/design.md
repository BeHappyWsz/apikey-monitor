# CCSwitch 导入支持设计（Claude / Codex）

**日期：** 2026-07-22  
**任务：** `.trellis/tasks/07-21-ccswitch-import-support/`  
**状态：** 已实现（v0.3.0）  

## 背景

本系统已有 `claude` / `codex` 导出，但内容是 shell `export` 片段，与 CC Switch 添加 Provider 时的粘贴格式、以及一键深链导入不一致。用户需要 **本系统 → 导入到 CCSwitch**，并 **自动填充基础信息**，尽量减少在 CCSwitch 内手改。

CC Switch 支持：

```
ccswitch://v1/import?resource=provider&app=<claude|codex>&name=...&endpoint=...&apiKey=...&model=...
```

以及 `config` + `configFormat=json` 的 Base64 完整配置导入（Claude 为 `{"env":{...}}`；Codex 为 `{"auth":{...},"config":"<toml>"}`）。

## 目标

1. 单条密钥可 **一键打开 CCSwitch 导入**（深链，预填基础字段）。
2. 同时提供 **可复制粘贴** 的 Claude JSON / Codex JSON 包装配置（深链不可用时的兜底）。
3. 仅本迭代支持 **claude** 与 **codex**。
4. 卡片增加独立 **「导入CCSwitch」** 按钮。
5. 现有 `env` / `powershell` / `json` 导出不回归。

## 非目标

- Gemini / OpenCode / OpenClaw 等其它 app
- 从 CCSwitch **反向导入** 到本库
- 批量一键导入多条到 CCSwitch
- 修改探测 / 严格验证逻辑
- 填写 CCSwitch 的 homepage / icon / 用量查询等本库不存在的字段

## 产品形态

### 方案：双轨（已确认）

| 轨道 | 行为 | 用途 |
|------|------|------|
| **主路径** | 生成并打开 `ccswitch://v1/import?...` | 本机已装 CCSwitch 时一键导入 |
| **兜底** | 文本区展示可粘贴配置 + 复制 | 协议未注册、浏览器拦截、跨机时 |

### 卡片

- 在卡片 footer 增加 **「导入CCSwitch」**（与「导出」并列）。
- 点击后：
  1. 按「应用选择规则」确定 `app`（claude / codex）。
  2. 若无法唯一判定：弹出轻量选择（仅两项：Claude / Codex），选后继续。
  3. 请求后端拿到 `{ deeplink, text, app }`。
  4. **优先** `window.location.href = deeplink`（或等价打开深链）。
  5. 同时 toast 提示「已尝试打开 CCSwitch；若未响应可复制配置」；提供快捷「复制粘贴配置」与可选「复制深链」。

### 导出弹窗（兼容）

- `claude` / `codex` 选项文案标明「可用于 CCSwitch」。
- 切换格式时 `text` 为粘贴配置；响应附带 `deeplink`（仅 claude/codex）。
- 增加按钮：**打开 CCSwitch 导入**、（可选）**复制深链**。
- `env` / `powershell` / `json` 不附带 deeplink、不显示打开按钮。

## 应用选择规则（卡片按钮）

| 条件 | 默认 app |
|------|----------|
| `model_probe_adapter === "anthropic_messages"` | `claude` |
| `model_probe_adapter` 为 `openai_chat` 或 `openai_responses` | `codex` |
| 仅 `supports_anthropic` 为真 | `claude` |
| 仅 `supports_openai` 为真 | `codex` |
| 两者皆真 / 皆假 / 无 adapter | **弹窗二选一**，不猜测 |

## 字段映射与 URL 规则（已确认）

| 本库 | Claude | Codex |
|------|--------|-------|
| `name`（空则用 host） | `name` | `name` |
| `base_url`（先 `normalize_base_url`） | **endpoint** = `join_api_path(base, "/anthropic")` | **endpoint** = `join_api_path(base, "/v1")` |
| `api_key` | `apiKey` | `apiKey` |
| `check_model` | 有则写 `model` 与 env 中的 `ANTHROPIC_MODEL`；**无则整段省略** | 有则写 `model` 与 toml `[general] model`；**无则整段省略** |
| `model_probe_adapter` | 不写入深链 | `openai_responses` → toml `wire_api = "responses"`；其它 openai 适配或未知 → `wire_api = "chat"`（Codex 段需要明确 wire 时） |

### URL 细节

- **Codex**：与现有 `export_config` 的 `openai_base` 一致，追加 `/v1`；`join_api_path` 已避免重复 `/v1`。
- **Claude**：统一追加 `/anthropic`。若规范化后 path **已以** `/anthropic` 结尾（大小写不敏感），则 **不再重复追加**。
- 控制字符校验沿用现有 export 规则；非法则 400，不静默写出。

### Provider slug（Codex TOML）

- 由 `name` 净化：小写、非 `[a-z0-9_]` 替换为 `_`、合并连续 `_`、去首尾 `_`。
- 空结果回退为 `custom`。
- TOML 段名：`[model_providers.<slug>]`。

## 导出文本格式（粘贴兜底）

### Claude（`fmt=claude`）

主输出改为 **JSON**（CC Switch / Claude settings 的 `env` 形态）：

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "<api_key>",
    "ANTHROPIC_BASE_URL": "<claude_endpoint>",
    "ANTHROPIC_MODEL": "<check_model 若有>"
  }
}
```

- 无 `check_model` 时 **不包含** `ANTHROPIC_MODEL` 键。
- 文件头不再使用 shell `export`（破坏性变更，UI/文档标明「CCSwitch / Claude env JSON」）。
- 需要 shell 时继续用 `env` / `powershell`。

### Codex（`fmt=codex`）

主输出改为 **JSON 包装**（与深链 `config` 解码形态一致，便于整段粘贴说明）：

```json
{
  "auth": {
    "OPENAI_API_KEY": "<api_key>"
  },
  "config": "[model_providers.<slug>]\nname = \"<display_name>\"\nbase_url = \"<codex_endpoint>\"\nwire_api = \"<responses|chat>\"\n\n[general]\nmodel = \"<check_model 若有>\""
}
```

- 无 `check_model` 时 **省略** `[general]` 整段（或仅有空 general 也不写 model 行；实现上 **不输出 `[general]` 段**）。
- `wire_api`：见上表。

### 深链生成

**URL 参数模式（优先，字段少、可读）：**

```
ccswitch://v1/import?resource=provider&app=<app>&name=<urlencoded>&endpoint=<urlencoded>&apiKey=<urlencoded>[&model=<urlencoded>]
```

- `model` 仅在 `check_model` 非空时追加。
- Claude/Codex 的 endpoint 分别按上表。

**可选增强（实现时若 URL 参数不足以带 wire_api，则 Codex 改用 config 模式）：**

- Codex 若需要 `wire_api`，使用  
  `configFormat=json&config=<base64(utf8(json))>`，  
  JSON 内容与粘贴 `text` 相同；`apiKey`/`endpoint`/`model` 仍可作 URL 覆盖参数（与 CC Switch 优先级一致）。
- 本迭代 **Codex 默认走 config Base64**（保证 wire_api / provider 段完整）；**Claude 默认走 URL 参数**（name/endpoint/apiKey/model），足够导入基础信息。若后续需 haiku/sonnet/opus 再升级 Claude 为 config 模式。

### API 响应

`GET /api/keys/{id}/export?fmt=claude|codex`：

```json
{
  "text": "<paste body>",
  "fmt": "claude",
  "deeplink": "ccswitch://v1/import?..."
}
```

其它 fmt：

```json
{ "text": "...", "fmt": "env" }
```

（无 `deeplink` 字段或为 `null`。）

卡片「导入CCSwitch」可复用同一接口：先按规则选定 `fmt`/`app`，再打开 `deeplink`。

不新增独立路由（减少面）；若后续需要「只返回 link 不返回 text」再拆。

## 安全

- 深链与粘贴文本含明文 API Key：与现有导出一致。
- **禁止** 将 deeplink 写入服务端日志 / toast 全文 / analytics。
- 复制深链时 toast 可用「已复制深链（含密钥，勿外传）」类提示。
- `export` 接口继续要求已登录会话（与现有一致）。

## 代码落点

| 文件 | 变更 |
|------|------|
| `core/export.py` | 重写 `_fmt_claude` / `_fmt_codex`；新增 `claude_endpoint` / `codex_endpoint` / `build_ccswitch_deeplink` / provider slug 辅助 |
| `api/router.py` | export 响应附带 `deeplink`（claude/codex） |
| `static/js/export_ui.js` | 打开深链、复制深链、文案 |
| `static/js/cards.js` | footer「导入CCSwitch」按钮 |
| 列表事件绑定处（如 `app.js` / list handlers） | 点击导入：选 app → 调 export → 开深链 |
| `static/index.html` | 导出弹窗按钮与选项文案 |
| `tests/test_core_db.py`（或 export 单测） | 格式快照、endpoint 规则、无 model 省略、deeplink 参数 |
| `docs/api.md` / `README.md` | 导入步骤与格式说明 |

## 测试方案

后端至少覆盖：

1. Claude：endpoint 为 `base + /anthropic`；已以 `/anthropic` 结尾不重复。
2. Codex：endpoint 为 `base + /v1`；已以 `/v1` 结尾不重复。
3. 有/无 `check_model`：有则含 model；无则 JSON/深链均不含 model。
4. Claude JSON 含 `ANTHROPIC_AUTH_TOKEN` 与 `ANTHROPIC_BASE_URL`。
5. Codex JSON 含 auth + config TOML 段；`openai_responses` → `wire_api = "responses"`。
6. `env` / `powershell` / `json` 行为不变。
7. deeplink 以 `ccswitch://v1/import?` 开头，含 `resource=provider` 与正确 `app`。
8. 控制字符密钥/URL 抛错。

前端检查：

1. 卡片可见「导入CCSwitch」。
2. 导出弹窗 claude/codex 可打开深链（有 deeplink 时）。
3. JS 语法检查通过。

## 验收标准

- [ ] 单条可导出 Claude 粘贴 JSON，endpoint 带 `/anthropic`，有 model 才含 model
- [ ] 单条可导出 Codex 粘贴 JSON，endpoint 带 `/v1`，有 model 才含 model
- [ ] 可生成并触发对应深链；无 CCSwitch 时仍可复制配置
- [ ] 卡片有独立「导入CCSwitch」入口
- [ ] env/powershell/json 不回归
- [ ] 单测 + 文档完成

## 已拍板决策

1. 方案 **C**：深链主路径 + JSON 粘贴兜底  
2. Codex 地址追加 **`/v1`**  
3. Claude 地址追加 **`/anthropic`**（已存在则不重复）  
4. 无 `check_model` → **省略** model 相关字段  
5. 卡片 **单独** 增加「导入CCSwitch」按钮  

## 开放实现细节（不阻塞，实现时按推荐）

- Codex 深链用 **config Base64**（推荐，保证 wire_api）  
- Claude 深链用 **URL 参数**（推荐）  
- 二选一弹窗 UI 用现有 modal 模式或轻量 confirm 级 UI，与站点风格一致  
