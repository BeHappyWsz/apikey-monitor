# PRD: 密钥面板监测与严格验证次数

## Goal
在密钥卡片面板展示每条密钥的「已监测次数」和「已严格验证次数」，次数持久化在库表中，并在对应检测路径递增。

## Scope
- `tbl_keys` 新增 2 个整型计数字段（默认 0）
- 连通性/健康监测落库时递增监测次数
- 严格模型验证落库时递增严格验证次数
- 密钥卡片 UI 展示并微调面板视觉
- SQLite + MySQL 迁移兼容

## Out of scope
- CCSwitch 导入（见任务 `07-21-ccswitch-import-support`）
- 重置计数、历史明细日志

## Acceptance
1. 新库与旧库启动后均具备 `monitor_count`、`strict_count` 字段，默认 0
2. `update_status` / 监测检测成功落库后 `monitor_count += 1`
3. `update_model_status` / 严格验证落库后 `strict_count += 1`
4. 列表/详情 API 返回这两个字段
5. 密钥卡片可见两项次数；布局在桌面与窄屏可读
6. 相关单测通过

## Field names
| DB column | Meaning | UI label |
|-----------|---------|----------|
| `monitor_count` | 连通性/健康检测次数 | 监测 |
| `strict_count` | 严格模型验证次数 | 严格验证 |
