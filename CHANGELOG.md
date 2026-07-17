# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 风格，版本号采用语义化版本。

## [Unreleased]

> 相对 [0.1.0] 的变更汇总。内容已与代码对齐，可直接作为 `0.1.1` 发布说明使用（版本号与 tag 待你确认后再 bump）。

### Added

- macOS / Linux 启动脚本 `start.sh`（`--no-browser`，可选 `--bg`，优先 `python3`）
- 系统设置打开时即显示 `0.0.0.0` 局域网风险提示；保存确认文案对齐
- 每条 Key 可选 **`check_path`**（仅相对路径）：覆盖 classify / health 探活默认入口；模型探测仍用内置 chat/messages 路径
- `check_path` 贯通：DB 迁移、API 校验、导入/导出 JSON、编辑页

### Changed

- **`core.py` → `core/` 包**：保持 `import core` 稳定；新增 `PROTOCOL_PROBES` / `EXPORT_FORMATS` / `IMPORTERS` 注册表，便于后续扩展协议与导出格式
- **前端模块拆分**：`static/app.js` 瘦身为编排层；列表/卡片/导出/操作等拆到 `static/js/*`（行为不变）
- 文档收口：明确本机单用户定位；**不做** Web 访问密码 / 公网鉴权；路线图去掉误导项
- README / 设计文档 / 启动路径与 CHANGELOG 同步
- `config.json` 作为运行时设置的原子写入目标（页面改设置后落盘）
- 定时监测（`health_check`）仅探测已成功协议；首次/均未成功时全量；失败不兜底其它协议，保留 `supports_*`（手动检测仍全量 `classify`）
- 启动前单实例收敛：`.runtime/server.pid`；重复启动先停旧实例再 bind

### Fixed

- 状态为 `up` 时清理残留探活错误：只聚合「最终胜出协议」的错误，避免 OpenAI-only 端点仍显示 Anthropic 404；`up` 卡片隐藏错误行；列表指纹纳入 `model_last_error`

### Planned（可选增强，非承诺）

- 可选密钥落盘加密（仍依赖本机目录权限；非必做）
- 监测历史 / 告警等体验增强（按需）
- 第三协议端到端（如 Gemini）：待产品选型后再开任务

## [0.1.0] - 2026-07-16

首个对外开源版本。

### Added

- 本地 API Key 管理：粘贴导入、手动添加、OpenAI / Anthropic 协议判别
- 定时监测：连通性、认证状态、延迟；全局与单条开关
- Web 管理：筛选、拖拽排序、编辑、批量检测 / 删除 / 导出
- 批量任务进度展示
- 配置导出：Claude Code、Codex CLI、`.env`、PowerShell、JSON；支持批量 JSON 与下载
- 列表刷新间隔可配置（监测设置，`0` 关闭主动轮询）
- 体验优化：工具栏「更多」、无选中禁用批量、`Ctrl+Enter` 保存、批量检测汇总与问题项筛选
- 列表卡片一键复制完整 API Key（`/api/keys/{id}/secret`）；列表接口脱敏
- JSON 备份 / 恢复：备份全部、导入识别同格式 JSON
- 空状态首次引导与导入示例
- 安全切换监听端口（失败回滚）
- 零第三方依赖（Python 3.10+ 标准库 + 现代浏览器）
- 基础单元测试与集成测试；CI 工作流示例（`docs/ci.workflow.example.yml`）
- MIT 许可证、README、CONTRIBUTING、CHANGELOG

### Security

- 列表与详情默认返回 `api_key_masked`，不暴露明文 Key
- 默认仅监听 `127.0.0.1`

### Changed

- JSON 导出字段精简为可移植配置：`name`、`base_url`、`api_key`、`check_model`
- 导出弹窗布局优化

[Unreleased]: https://github.com/BeHappyWsz/apikey-monitor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/BeHappyWsz/apikey-monitor/releases/tag/v0.1.0
