# PRD: 在线筛选要求秘钥与模型均正常

## Goal
快捷筛选「在线」只展示**秘钥连通正常且模型无严格异常**的 Key；模型异常仍由「异常/问题」覆盖。

## Background
- 当前 `up` 仅看 `status === "up"`（连通性），可能包含 `model_status` 为 rate_limited/degraded/down/auth_error 的项。
- 「异常」(issue) / 「问题」(problem) 已纳入严格模型验证失败。
- 用户期望「在线」= 秘钥 + 模型均正常。

## Acceptance
1. `status_filter=up`：仅 `status=up` 且**不**满足严格模型问题条件（`model_verification_version>=1` 且 `model_status in down/auth_error/rate_limited/degraded`）。
2. `summary.up` 计数与上述定义一致；`summary.problem` 仍为非在线（`total - healthy_up`）。
3. 前端本地筛选 `getVisibleKeys(..., "up")` 与 fallback `countStatuses` 一致。
4. 未做严格验证（`model_verification_version<1`）或模型仍 unknown 的 `status=up` 仍算在线（仅连通正常、模型未确认异常）。
5. 单测覆盖：后端 page summary/filter、前端 state filtering。

## Out of scope
- 改探测逻辑、状态写入、卡片展示文案（除筛选 title 微调）
