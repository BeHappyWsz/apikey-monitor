# Design — Fix Anthropic capability probe reliability

## 问题本质

Anthropic 能力探测 = 真实 `/messages` 生成。语义已正确（200=支持，其它=失败），但默认超时 15s < 慢/推理网关生成耗时（实测 5–37s）+ 偶发 502 → 可用端点被误判「不支持」、`supports_anthropic` 横跳。

**结论**：不改判定逻辑。① 把超时调到「生成来得及完成」（45s）；② 对瞬时失败重试，穿透偶发 502/超时。

（「缺 model 触发 400 视为支持」的轻量捷径已否决——用户要求真实生成跑通才算成功。）

## 改动点

### 1. 默认超时 15 → 45（三处）
- `db.py._FALLBACK_DEFAULTS["request_timeout_sec"]`、`config.json`、`api/validators.py`（`.get` 默认 + `normalize_int` 默认）。区间 3–120 不变。

### 2. 一次性迁移（`db.py._migrate()`）
- 读 `settings.request_timeout_sec`；若 `== "15"`（旧默认）则 `UPDATE` 为 `"45"`。仅迁移旧默认，不覆盖自定义值。幂等。

### 3. anthropic 探针重试（`core/protocols/anthropic.py`）
- `_MAX_ATTEMPTS = 3`、`_is_transient(code) = code == 0 or code >= 500`。
- `probe()`：外层 `for _ in range(_MAX_ATTEMPTS)`，内层仍按候选 URL 探测；每次得到结果后：`status=="up"` 或 `not _is_transient` → 立即返回；否则重试。3 次仍瞬时失败 → 返回最后结果（down/degraded）。
- 仅 anthropic 探针重试；OpenAI（`GET /models`）不重试。`model_probe` 本轮不改。

### 4. UI 说明 + 文案
- `static/index.html` 请求超时字段加 `title=` + `（建议≥45）`。
- 探针消息体 `"ping"` → `"hi"`。

## 不改动（确认）

- `_record_http`、`probe.py` 聚合/状态优先级、`http.py`、`key_service.py`、前端、DB schema、`model_probe`、校验区间。

## 数据流

```text
classify / health_check
  -> openai.probe:    GET /models (timeout=45, ~1-2s) -> 200 -> up
  -> anthropic.probe: POST /messages 真实生成 (timeout=45, ~5-37s)
                      瞬时失败(5xx/0) -> 最多重试2次 -> 200 -> up
  -> supports_anthropic = (anthropic up) = true
```

## 兼容性 / 风险

- 慢但可用的端点 `supports_anthropic` 从「常 false」→「稳定 true」（修复性）。
- 现有库旧默认 15 迁移到 45；自定义值保留。
- 监测定时跑真实生成 + 重试：常态 1 次成功（~5–37s），偶发重试；不支持的端点（/messages 404）仍秒回、不重试。真·挂死端点最坏 3 次×45s（罕见，受 `concurrency`/tick 上限约束）。
- 既有 mock 测试不依赖真实超时，不受影响（已验证）。

## 回滚

改动文件：`db.py`、`config.json`、`api/validators.py`、`static/index.html`、`core/protocols/anthropic.py`、`docs/design.md`、`CHANGELOG.md`、测试。逐文件 revert；迁移回退 = 手动改 settings 表回 15。
