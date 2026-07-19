# Primary storage and cache

`db.py` keeps the existing module-level API while selecting one durable primary
store at startup:

- `sqlite` (the default): the local `data.db` file.
- `mysql`: a MySQL 8.0+ database, using `utf8mb4` and a transaction per write.

Set `_storage_backend` in the private startup configuration, or set
`APIKEYCONFIG_STORAGE_BACKEND` to override it for a process.  MySQL connection
options can be supplied either by the private configuration seed or by these
environment variables, which take precedence and are intended for containers:

```text
APIKEYCONFIG_MYSQL_HOST
APIKEYCONFIG_MYSQL_PORT
APIKEYCONFIG_MYSQL_DATABASE
APIKEYCONFIG_MYSQL_USERNAME
APIKEYCONFIG_MYSQL_PASSWORD
APIKEYCONFIG_REDIS_HOST
APIKEYCONFIG_REDIS_PORT
APIKEYCONFIG_REDIS_DB
APIKEYCONFIG_REDIS_USERNAME
APIKEYCONFIG_REDIS_PASSWORD
```

On startup, `db.init_db()` creates or upgrades `tbl_keys`, `tbl_settings`,
`tbl_users`, and `tbl_sessions`; the session table has a foreign key to users
and the monitor/session indexes are created with the schema. Connection
passwords are never returned from the HTTP API, included in backups, or
written to logs. Avoid committing a configuration file that contains real
connection passwords.

## Table-name upgrade and recovery

Existing databases using the legacy `keys`, `settings`, `users`, and `sessions`
names are upgraded in place to the `tbl_*` names at startup. The migration
preserves rows, primary keys, indexes, and the session-to-user foreign key. It
is idempotent: starting again after a successful rename makes no further
schema-name changes.

Before deploying this release, make a restorable backup while the application
is stopped: copy the SQLite database file, or create a MySQL logical backup.
If both a legacy table and its `tbl_*` target already exist, startup stops with
a collision error and makes no merge or deletion; restore or reconcile from
the backup before retrying. After the new version has written data, recover to
the old application version by restoring the pre-upgrade backup rather than
trying to merge reverse-renamed tables.

Redis is optional and is currently activated only with the MySQL primary
store.  It is a read-through cache for masked API-key lists/details and public
settings only.  Entries expire after 60 seconds and all committed key/settings
writes invalidate them.  Redis failure or restart simply falls back to MySQL;
it does not block API requests.  API keys, password hashes, sessions, and
private settings are never cached.

To exercise a configured real MySQL/Redis deployment, run:

```bash
APIKEYCONFIG_TEST_MYSQL_REDIS=1 python -m unittest tests.test_mysql_redis_integration -v
```

The integration test creates timestamped records and removes them afterwards.
