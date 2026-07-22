# PRD: 普通用户与管理员权限控制

## Status
`planning` — **需求未定**，本任务仅沉淀权限分析与待拍板点，**不进入实现**。

## Goal
在现有「全员管理员」模型上引入 **管理员 / 普通用户** 角色，对敏感动作做权限控制；具体开放范围等产品拍板后再设计与实现。

## Background（现状）

- 所有登录账号都是管理员：`docs/authentication.md` 明确 *All accounts are administrators*，无 `role` / 租户 / 自助注册。
- `tbl_users` 字段：`id, username, password_hash, must_change_password, enabled, created_at` — **无 role**。
- 除 `GET /api/system/health`、`GET /api/auth/bootstrap`、`POST /api/auth/login` 外，任意已登录用户可访问全部 API。
- 密钥为**全局共享池**（无 `owner_user_id`）；列表默认 mask，明文走 `secret` / export。
- 用户管理 API 已有但**无 admin 校验**：
  - `GET /api/auth/users`
  - `POST /api/auth/users`
  - `PUT /api/auth/users/{id}`（启用/禁用）

### 相关代码入口
- 鉴权：`services/auth_service.py`（`AUTH.login` / `current` / `create_user` / `set_user_enabled`）
- 路由：`api/router.py`（`_authenticated_session` 仅校验登录 + CSRF + 强制改密）
- 前端：`static/js/auth.js`（用户列表/创建/禁用）、设置/同步/导出/密钥操作全员可见

---

## Open Decisions（必须先拍板）

### D1. 数据归属模型
| 选项 | 含义 | 影响 |
|------|------|------|
| **A. 共享实例**（贴近现状） | 全员同一 Key 池；角色只控「能做什么」 | 改动小：加 role + 路由守卫 + UI 隐藏 |
| **B. 按用户隔离** | Key 归属用户；普通用户只能操作自己的资源 | 需 `owner_user_id`、查询过滤、迁移策略 |

### D2. 普通用户能否接触明文密钥？
- 否：`secret`、所有 export（含 `export_all` / batch_export / 单条 export）仅 admin
- 是：至少审计 + 限流；仍建议 `export_all` 仅 admin

### D3. 普通用户能否触发检测 / 改 Key 数据？
- 只读看板：仅 list / page / history / revision
- 值班运维：只读 + 单条 check / check_model（限流），禁止增删改/导入/排序
- 协作编辑：共享池下开放增删改（风险高，需明确责任）

### D4. 首个账号与升级兼容
- bootstrap 用户是否强制 `admin`
- 已有库中存量用户默认 `admin` 还是需手工指定
- 是否允许最后一个 admin 被禁用/降级（建议禁止）

---

## 权限矩阵草案（共享实例 A + 保守默认）

> 拍板前仅作 backlog 参考；最终以 D1–D3 为准。

### 必须管理员（P0）
| 动作 | API / 入口 | 原因 |
|------|------------|------|
| 用户列表 / 创建 / 启停 | `GET|POST /api/auth/users`，`PUT /api/auth/users/{id}` | 账号与封禁 |
| 保存设置 | `POST /api/settings` | 并发、间隔、端口等全局影响 |
| WebDAV 配置/测试/上传/下载/状态 | `/api/sync/*` | 凭据 + 全量导出/覆盖 |
| 安全重启 | `POST /api/system/restart`，`GET .../restart/{id}` | 进程级 |
| 明文密钥 | `GET /api/keys/{id}/secret` | 泄密 |
| 导出（单/批/全量） | `.../export`，`batch_export`，`export_all` | 含密钥 |
| 删除（单/批） | `DELETE /api/keys/{id}`，`batch_delete` | 不可逆 |

### 建议管理员（P1，共享池）
| 动作 | API | 说明 |
|------|-----|------|
| 新增 / 批量 / 导入解析 | `POST /api/keys`，`/batch`，`/import/parse` | 污染共享池、恶意 endpoint |
| 编辑 Key | `PUT /api/keys/{id}` | 改 URL/密钥/模型 |
| 排序 | `reorder` / `move` | 全局顺序 |
| 批量检测 | `batch_check` | 配额；单条检测可按 D3 放开 |
| 读 settings 中的运维细节 | `GET /api/settings` | 可对 user 做字段级裁剪 |

### 普通用户通常可保留
| 动作 | API |
|------|-----|
| 登录 / 登出 / 改自己密码 / me | auth 自助 |
| 列表 / 分页筛选 / revision | `GET /api/keys`，`/page`，`/revision`（masked） |
| 单条 masked 详情 / 历史 | `GET /api/keys/{id}`，`.../history` |
| 健康检查 | `GET /api/system/health`（已公开） |
| 可选：单条检测 / 严格验证 / 任务进度 | 取决于 D3；需限流 |

### 两类角色共用（非角色差异）
- Session + CSRF、must_change_password、禁用废 session、登录限流
- 列表默认 mask；明文仅 secret/export 且受角色控制

---

## 建议落地顺序（需求确定后）

1. **产品确认** D1–D4，冻结「保守默认」或定制矩阵  
2. **Schema**：`tbl_users.role`（`admin` \| `user`）；bootstrap + 存量迁移策略  
3. **Auth**：`AUTH.current` / `me` / login 返回 `role`；`require_admin` 辅助  
4. **Router**：按矩阵挂守卫（以后端 403 为准，不靠前端隐藏）  
5. **Frontend**：`auth.js` / 设置 / 同步 / 导出 / 卡片操作按 role 隐藏；403 toast  
6. **测试**：admin 全通；user 打 P0/P1 接口均 403；回归登录/CSRF/改密  
7. **文档**：`docs/authentication.md`、`docs/api.md`、CHANGELOG  
8. **可选 P2**：操作审计（secret / export / delete / settings）

---

## Out of Scope（本任务当前阶段）
- 不写代码、不改表、不改路由
- 不做租户/SSO/自助注册/邮箱找回
- 不实现资源级 ACL（除非 D1 选 B 后再开子任务）

## Acceptance（仅文档阶段）
- [x] 现状与风险点写入本 PRD
- [x] 开放决策 D1–D4 列出
- [x] 权限矩阵草案与实现顺序可指导后续设计
- [ ] 产品拍板 D1–D4 后：补 `design.md`，再 `task.py start` 进入实现

## References
- `docs/authentication.md`
- `docs/api.md`（Authentication / Key / Settings / Sync / System）
- `api/router.py`、`services/auth_service.py`、`db.py`（users/sessions）
- `static/js/auth.js`
