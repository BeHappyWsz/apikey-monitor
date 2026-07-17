# PRD: 多机数据共享与坚果云 WebDAV 同步（Phase 1 MVP）

## Status

**In progress.** 2026-07-17 已恢复并实现 Phase 1 MVP：WebDAV 配置、测试连接、上传、下载合并/替换、文档与单元测试。
当前剩余工作：最终检查、提交、按 Trellis 流程归档。

- **优先级**：P2
- **创建**：2026-07-17
- **触发来源**：开源单机场景下「多电脑共用配置」；对标 cc-switch 式坚果云 WebDAV 上传/下载管控

## Goal

在不破坏「本机单用户、零第三方依赖、默认仅 127.0.0.1」定位的前提下，提供可选的 **多机配置统一** 能力：

1. 以 **JSON 备份载荷** 为真相源（优先于直接同步 `data.db`）
2. 可选对接 **WebDAV**（坚果云等），支持 **测试连接 / 上传 / 下载**
3. 下载侧支持 **合并导入** 与 **全量替换**，冲突策略用户可控
4. 文档写清单写者约定、安全边界与推荐工作流

## Background / Context

| 现状 | 说明 |
|------|------|
| 数据 | SQLite `data.db` 明文 Key；`config.json` 为运行时设置 |
| 已有 | JSON 备份/恢复、粘贴导入、`APIKEYCONFIG_DB_PATH` / `APIKEYCONFIG_CONFIG_PATH` |
| 定位 | 本机运维小工具，无 Web 登录；不适合默认做成公网多用户服务 |
| 对标 | cc-switch：WebDAV 为配置中枢，显式上传/下载，而非静默双向实时多写 |

用户诉求：**像 cc-switch 一样，配置统一到坚果云，通过 WebDAV 管控上传、下载。**

## User stories（恢复后可裁剪）

1. 作为个人用户，我能在 A 电脑导出配置，在 B 电脑导入，无需 Git。
2. 作为个人用户，我能配置坚果云 WebDAV，一键上传当前 Key 列表到云端路径。
3. 作为个人用户，我能从云端下载并合并/替换到本机库。
4. 作为用户，我能测试 WebDAV 是否连通，并看到云端文件时间，避免盲覆盖。
5. 作为用户，我的 WebDAV 密码与 API Key 不会出现在列表接口或日志明文中。

## Phased plan

### Phase 0 — 文档与约定

- [x] README / design：多机使用方案对比（JSON 备份、外置 DB、WebDAV、内网单服务）
- [x] 明确 **单写者**：同一 `data.db` / 同一 WebDAV 文件，同时只允许一台在写
- [x] 文档说明环境变量 `APIKEYCONFIG_DB_PATH` 用法与风险（网盘同步 DB）
- [x] 安全警告：备份/云端文件 = 全量密钥

### Phase 1 — MVP WebDAV

- [x] 设置页：WebDAV `server` / `username` / `password` / `remote_path`
- [x] 密码本地持久化；API 仅返回「是否已设置」，不回传明文
- [x] **测试连接**（HEAD / PROPFIND / 轻量 GET）
- [x] **上传**：当前库 → 与现有备份同结构的 JSON → WebDAV `PUT`
- [x] **下载**：WebDAV `GET` → 用户选 **合并（跳过重复）** 或 **全量替换** → 走现有 import
- [x] 展示上次同步结果、远程 `Last-Modified`（若可得）
- [x] **零第三方依赖**：`urllib` + Basic Auth + HTTPS
- [x] 单元测试：URL 拼接、路径规范化、导入合并去重逻辑（可 mock HTTP）
- [x] README：坚果云示例（`https://dav.jianguoyun.com/dav/`、应用密码、路径示例）

**坚果云参考（写入文档即可）：**

| 项 | 值 |
|----|-----|
| 服务器 | `https://dav.jianguoyun.com/dav/` |
| 用户名 | 登录邮箱 |
| 密码 | 账号中的 **应用密码**（非登录密码） |
| 路径示例 | `/apikey-monitor/backup.json` |

### Phase 2 — 体验与安全增强（可选）

- [ ] 启动时可选提示「云端有更新」
- [ ] 本地变更后可选提示「是否上传」
- [ ] 端到端加密备份包（同步口令）；评估是否破零依赖（stdlib 无 AES）
- [ ] `MKCOL` 自动创建远程目录
- [ ] 上传前「先拉再合再推」防互相踩

### Phase 3 — 非目标 / 明确不做（除非产品改向）

- [ ] ~~无鉴权下默认监听 0.0.0.0 做多用户~~
- [ ] ~~实时双向自动狂同步且无提示~~
- [ ] ~~默认把运行中 `data.db` 当 WebDAV 对象强推~~
- [ ] ~~中心账号 SaaS / 第三方云 SDK 强依赖~~

## Sync payload 约定（草案）

优先同步 **JSON 配置备份**（与「备份全部」字段对齐），而非整库文件：

- 至少：`name`, `base_url`, `api_key`, `check_model`, `check_path`
- 可选是否带监测开关/备注（实现时再定）
- **不**把 `config.json` 的 host/port 强行多机共用（端口/本机绑定应本机独立）

## Conflict policy（草案）

| 策略 | 用途 |
|------|------|
| 下载 + 合并 | 按 `base_url + api_key`（或规范化后）去重；默认跳过已有 |
| 下载 + 全量替换 | 以云端为准（需二次确认） |
| 上传 | 默认覆盖远程同路径文件（显示远程时间） |

## Security requirements

1. WebDAV 密码与 API Key 不得进前端列表日志、不得进 GET 设置接口明文。
2. 导出/上传操作需用户显式触发（MVP）；自动同步仅 Phase 2 且需可关。
3. README 声明：共享坚果云账号 = 共享全部 Key；建议应用密码可吊销。
4. 默认仍绑定本机；WebDAV 是可选能力，不是远程打开管理面。

## Acceptance criteria（整包完成时；可按 Phase 分期勾选）

- [ ] Phase 0 文档用户能按文完成「手动 JSON 多机」与「外置 DB 单写者」
- [ ] Phase 1：填写坚果云 WebDAV 后可测试连接、上传、下载合并/替换
- [ ] 全程无新增 pip 依赖（Phase 1）
- [ ] 设置接口脱敏；测试覆盖合并与路径/认证头构造
- [ ] CHANGELOG / README 同步

## Open questions（开始实现前确认）

1. MVP 是否必须加密云端 JSON，还是 HTTPS + 应用密码 + 警告即可？
2. 下载全量替换时是否先自动本地备份一版？
3. WebDAV 设置存在 `config.json` 还是 `data.db` settings 表？（倾向与现有 settings 一致）
4. 是否需要子任务拆分：`docs-multi-device` / `webdav-mvp` / `webdav-encrypt`？

## Related local notes（会话结论摘要）

- 多机需求分 A 迁移 / B 实时共用 / C 单服务多浏览器；优先 A + 显式 WebDAV。
- 网盘直接同步 `data.db` 有双开、WAL、重复探活风险，文档可提但不作为主推。
- 与 cc-switch 对齐的是 **文件中枢 + 上传下载管控**，不是改成公网服务。

## Non-goals

- 不替代第三协议等其它 backlog（如 `07-16-third-protocol-e2e`）
- 不在未确认加密方案前引入第三方密码学库

## Resume checklist

1. 跑完整验证
2. 更新必要文档 / spec
3. 提交并按 Trellis 流程归档
