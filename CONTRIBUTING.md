# 贡献指南

感谢你愿意改进 **apiKeyConfig**。本项目目标是保持小而专注：本地运行、固定且明确的运行依赖、开箱即用。

## 开发环境

- Python **3.10+**
- `requirements.txt` 中固定的 Python 包（`argon2-cffi`、`PyMySQL`、`redis`）
- 可选：Node.js 18+（前端语法检查 / `state` 单测）

```bash
python -m pip install -r requirements.txt
python app.py
python -m unittest discover -s tests -v
node --check static/app.js
node --test tests/state.test.mjs
```

## 原则

1. **依赖保持克制且可复现**：运行依赖必须固定在 `requirements.txt`；新增、移除或升级依赖前请先在 Issue 讨论。
2. **密钥安全**：列表/详情接口不要返回明文 `api_key`；完整密钥仅限 secret / 导出 / 检测路径。默认绑定本机；现有管理员登录、会话和 CSRF 保护不得被削弱。
3. **小步提交**：一个 PR 聚焦一件事；附上测试或手工验证步骤。
4. **兼容本地数据**：变更 SQLite schema 时提供迁移或向后兼容路径（见 `db.py`）。

## 建议工作流

1. Fork 并创建分支：`feat/...`、`fix/...`、`docs/...`
2. 修改代码与文档
3. 跑通测试
4. 打开 Pull Request，说明动机、行为变化与风险

## 提交说明

推荐使用简洁英文或中文 commit message，例如：

- `feat: support JSON import for backup restore`
- `fix: keep api_key when partial update is empty`
- `docs: clarify list desensitization`

## 安全问题

若发现可导致密钥泄露的漏洞，请**不要**公开 Issue 细节，优先私下联系维护者；修复前避免在日志/示例中粘贴真实 Key。

## 行为准则

请保持友善、就事论事。不接受骚扰、人身攻击或恶意破坏。
