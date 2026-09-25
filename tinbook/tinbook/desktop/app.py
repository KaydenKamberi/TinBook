"""Minimal CP0 desktop launcher; the full app is owned by CP2A."""

from __future__ import annotations

import argparse
import socket
import threading

from flask import Flask
from werkzeug.serving import make_server


def create_app() -> Flask:
    """Create the CP0 health page."""
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return "Tinbook OK"

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Tinbook")
    parser.add_argument("--browser", action="store_true", help="serve the browser preview")
    args = parser.parse_args()
    app = create_app()

    if args.browser:
        app.run(host="0.0.0.0", port=5000)
        return

    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        import webview

        webview.create_window("Tinbook", f"http://127.0.0.1:{server.server_port}")
        webview.start()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()