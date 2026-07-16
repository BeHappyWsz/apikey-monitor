# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 风格，版本号采用语义化版本。

## [Unreleased]

### Added

- macOS / Linux 启动脚本 `start.sh`（`--no-browser`，可选 `--bg`，优先 `python3`）
- 系统设置打开时即显示 `0.0.0.0` 局域网风险提示；保存确认文案对齐
- README / 设计文档 / 启动路径与 CHANGELOG 同步

### Changed

- 文档收口：明确本机单用户定位；**不做** Web 访问密码 / 公网鉴权；路线图去掉误导项

### Planned（可选增强，非承诺）

- 可选密钥落盘加密（仍依赖本机目录权限；非必做）
- 监测历史 / 告警等体验增强（按需）


## [0.1.0] - 2026-07-16

首个对外开源版本。

### Added

- 本地 API Key 管理：粘贴导入、手动添加、OpenAI / Anthropic 协议判别
- 定时监测：连通性、认证状态、延迟；全局与单条开关
- Web 管理：筛选、拖拽排序、编辑、批量检测 / 删除 / 导出
- 批量任务进度展示
- 配置导出：Claude Code、Codex CLI、`.env`、PowerShell、JSON；支持批量 JSON 与下载
- 列表刷新间隔可配置（监测设置，`0` 关闭主动轮询）
- 体验优化：工具栏「更多」、无选中禁用批量、`Ctrl+Enter` 保存、批量检测汇总与问题项筛选、卡片一键 Codex/Claude
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
