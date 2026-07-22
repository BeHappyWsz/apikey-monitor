# PRD: 支持导入到 CCSwitch（Claude / Codex 优先）

## Goal

让本系统中的密钥配置，能以 **CC Switch 可直接导入** 的方式导出：优先 **深链一键打开**，并提供 **JSON 粘贴兜底**。本迭代 **只做 claude / codex**；其它工具后续再扩展。自动填充 name / endpoint / apiKey / model（有则），尽量减少在 CCSwitch 内手改。

## Background

- 面板接入建议已提示「可直接接入 ccswitch」，但当前导出仍是 shell `export`，与 CC Switch Provider 导入不一致。
- CC Switch 支持 `ccswitch://v1/import?resource=provider&app=...` 深链与 config Base64 导入。
- 方向：**本系统 → 导入到 CCSwitch**。反向导入后续单列。

## Scope（P0）

### In

1. **Claude**：粘贴用 `{"env":{ANTHROPIC_*}}` JSON；endpoint = base + `/anthropic`；深链 `app=claude`。
2. **Codex**：粘贴用 `{"auth","config"}` JSON（config 为 TOML 字符串）；endpoint = base + `/v1`；深链 `app=codex`（config 模式可带 wire_api）。
3. 有 `check_model` 才写入 model；无则省略。
4. UI：导出弹窗 claude/codex 标明 CCSwitch；**打开 CCSwitch 导入**；卡片独立 **「导入CCSwitch」**。
5. 测试 + `README` / `docs/api.md`。

### Out

- Gemini / OpenCode 等其它 app
- CCSwitch → 本系统反向导入
- 批量一键导入多条到 CCSwitch
- 修改探测/严格验证
- homepage / icon / haiku·sonnet·opus 三分模型（单 check_model 只填主 model）

## Requirements

1. `export_config(..., "claude")` 产出可粘贴 JSON；含 AUTH_TOKEN 与 BASE_URL（endpoint 含 `/anthropic`）。
2. `export_config(..., "codex")` 产出可粘贴 JSON；含 api key 与 base_url（endpoint 含 `/v1`）。
3. 导出 API 对 claude/codex 返回 `deeplink`。
4. 不破坏 env / powershell / json。
5. 控制字符校验与现有一致。

## Acceptance Criteria

- [ ] Claude / Codex 粘贴格式与 endpoint 规则符合 design
- [ ] 深链可打开（本机已装 CCSwitch）；失败时可复制配置
- [ ] 卡片有「导入CCSwitch」
- [ ] 无 check_model 时省略 model
- [ ] 单测与文档完成
- [ ] env/powershell/json 不回归

## Design

见同目录 `design.md` 与 `docs/superpowers/specs/2026-07-22-ccswitch-import-design.md`。

## Notes

- 相关：`core/export.py`、`static/js/export_ui.js`、`static/js/cards.js`、`api/router.py`、`docs/api.md`
