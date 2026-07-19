# Fix Anthropic capability probe reliability

## Goal

让 Anthropic 协议能力探测在慢/推理型网关上**稳定正确**：真实发送 `/messages` 生成请求，**收到 200 才算成功（支持），其它一律失败**；并对瞬时失败重试，避免可用端点被误判。

## Background（诊断，2026-07-17，id=4 `https://api.aisenyu.com/v1`）

- DB 存 `supports_anthropic=1`，实时 `classify` 却返回 false（横跳）；端点正常：`/models` 200、`/messages` 真实生成 200。
- 根因：默认 `request_timeout_sec=15`；anthropic 探针是**真实生成**，reasoning 网关上一次生成 **5–37s**（实测最大 37.4s）且偶发 502，15s 必然超时 → `supports_anthropic=false`。
- 探针成功语义已正确（200→up→supports），无需改判定逻辑。

## 最终方案（实测驱动，迭代后定稿）

起初考虑「缺 model 触发 400 视为支持」的轻量捷径 —— **用户否决**，要求真实生成跑通才算成功。随后实测发现：
- timeout=30 仍不够（偶现 31–37s 运行）；
- 偶发 502（约 1/12，上游瞬时错误，与超时无关）。

故定稿为 **默认超时 15→45 + 瞬时失败重试 2 次**。

## Requirements

- **R1** 默认 `request_timeout_sec` 15 → 45（`db.py._FALLBACK_DEFAULTS`、`config.json`、`api/validators.py`）。区间 3–120 不变。
- **R2** 现有库一次性迁移：`db.py._migrate()` 中若值为旧默认 `"15"` 则更新为 `"45"`（不覆盖用户自定义值）。
- **R3** 设置 UI（`static/index.html`）请求超时字段加说明/提示（建议 ≥45s，过低会误判）。
- **R4** anthropic 探针对**瞬时失败**（5xx / 超时 / 连接错误）最多重试 2 次（共 3 次），任一次 200 即成功；确定性结果（200/4xx/401/403/404）立即返回不重试。OpenAI（`/models`）探针不重试。
- **R5** 探针消息体 `"ping"` → `"hi"`（与用户描述一致，纯文案）。判定逻辑/状态语义/`_record_http`/聚合/前端/DB schema **不变**。

## Acceptance Criteria（已验证 ✅）

- [x] aisenyu `classify` 连跑 3 次：`supports_anthropic` 稳定 true（实测 3/3 = True，http 200）。
- [x] 真实 `/messages` 200 → supports_anthropic=true；非 200 → false（语义未回归）。
- [x] 全新库默认 45；旧值 15 迁移为 45；自定义值（20/10）保留（4 用例验证）。
- [x] 重试单测：5xx→重试成功、timeout→重试成功、持续 5xx→3 次后 degraded、401/404→不重试（5 用例）。
- [x] `tests.test_probe_instance` / `test_core_db` 全绿（14 + 35）。
- [x] 设置 UI 请求超时字段有可见说明。
- [x] `docs/design.md` 同步（超时 45 + 重试 + 语义）。

## Out of Scope

- 探针判定逻辑/状态语义改造（已正确）。
- 轻量「快速失败」捷径（已否决）。
- 第三协议、SSE 流式、监测历史/告警、前端徽章/DB schema 变更。
- `model_probe`（model_check）的重试（本轮仅改能力探针；如需可后续对称补）。
