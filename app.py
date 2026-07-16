# -*- coding: utf-8 -*-
"""Application assembly and HTTP server lifecycle."""
import argparse
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer

import db
import monitor
from api.handler import Handler


class AppServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main(argv=None):
    parser = argparse.ArgumentParser(description="API Key 配置与监测面板")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--restart-id", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    db.init_db()
    settings = db.get_all_settings()
    host = args.host or settings.get("server_host", "127.0.0.1")
    port = args.port or int(settings.get("server_port", 7878))
    runtime = dict(settings); runtime.update(server_host=host, server_port=str(port))
    server = AppServer((host, port), Handler)
    server.runtime_settings = runtime
    monitor.start()
    display_host = "127.0.0.1" if host in ("0.0.0.0", "localhost") else host
    url = f"http://{display_host}:{port}"
    print(f"[apiKeyConfig] 服务已启动: {url}")
    print(f"[apiKeyConfig] 数据库: {db.DB_PATH}")
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(.8), webbrowser.open(url)), daemon=True).start()
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        print("\n[apiKeyConfig] 正在退出…")
    finally:
        monitor.stop()
        server.server_close()


if __name__ == "__main__":
    main()
