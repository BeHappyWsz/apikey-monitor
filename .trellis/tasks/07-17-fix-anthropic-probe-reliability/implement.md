# Implement — Fix Anthropic capability probe reliability

## 已完成改动

- `db.py`：`_FALLBACK_DEFAULTS["request_timeout_sec"]` 15→45；`_migrate()` 末尾迁移旧默认 `"15"`→`"45"`（仅旧默认，保留自定义值）。
- `config.json`：seed `"15"`→`"45"`。
- `api/validators.py`：fallback `15`→`45`（两处）。
- `static/index.html`：请求超时字段加 `（建议≥45）` + `title=` 说明。
- `core/protocols/anthropic.py`：`probe()` 加重试（`_MAX_ATTEMPTS=3`、`_is_transient`）；瞬时失败（5xx/超时/连接）最多重试 2 次，确定性结果立即返回；消息体 `"ping"`→`"hi"`。
- `tests/test_probe_instance.py`：新增 `AnthropicRetryTests`（5 用例）。
- `docs/design.md`、`CHANGELOG.md`：同步说明。

## 验证结果（2026-07-17）

- **aisenyu classify ×3**：`supports_anthropic=True` 3/3，anthropic http=200，status=up（稳定，修复前横跳 false）。
- **迁移**：fresh→45、旧 15→45、自定义 20/10 保留（4 用例）。
- **单测**：`test_probe_instance` 14/14、`test_core_db` 35/35 全绿；含 5 个新重试用例。
- **既有失败**：`test_webdav`/`test_sync_service` 共 5 个 `WinError 10054` —— 在**纯净树**（stash 我的改动）同样失败，是 Windows 套接字环境问题，与本改动无关。

## 验证命令

```bash
python -m unittest tests.test_probe_instance tests.test_core_db -v   # 探针+核心
python -m unittest discover -s tests -v                              # 全量（5 个 webdav/sync 为既有环境失败）

# aisenyu 稳定性（应稳定 supports_anthropic=true）
python -c "import sqlite3,core.probe as p; k=sqlite3.connect('data.db').execute('SELECT base_url,api_key,check_model,check_path FROM keys WHERE id=4').fetchone(); [print(p.classify(k[0],k[1],45,k[2] or '',k[3] or '')['supports_anthropic']) for _ in range(3)]"
```

## 回滚点

逐文件 `git checkout -- <file>`；迁移回退 = 手动改 settings 表 `request_timeout_sec` 回 15。
