# PRD: 后续拓展 — 支持 CCSwitch 导入

## Goal
支持从 CCSwitch 导出的配置/格式导入到本系统密钥库。

## Status
Deferred — 本迭代不实现。当前密钥面板专注监测与严格验证次数展示。

## Future notes
- 调研 CCSwitch 配置文件结构与字段映射（base_url / api_key / model / adapter）
- 复用现有 `/api/import/parse` 与 batch 入库链路
- 导入后可选择是否立即检测 / 严格验证
- 与现有 JSON / 文本粘贴导入并存，避免破坏现有格式

## Acceptance (when implemented)
1. 用户可粘贴或上传 CCSwitch 导出内容并预览候选
2. 合法条目可批量入库，重复项可跳过
3. 文档说明支持的 CCSwitch 版本/字段
