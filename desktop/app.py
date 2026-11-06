"""Launch Tinbook in a desktop window or browser mode."""

from __future__ import annotations

import argparse
import threading

from werkzeug.serving import make_server

from .server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Tinbook")
    parser.add_argument("--browser", action="store_true", help="serve the browser preview")
    args = parser.parse_args()
    app = create_app()
    server = None
    thread = None
    try:
        if args.browser:
            app.run(host="0.0.0.0", port=5000, use_reloader=False, threaded=True)
            return

        import webview

        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        webview.create_window(
            "Tinbook", f"http://127.0.0.1:{server.server_port}",
            width=420, height=720, min_size=(360, 560),
        )
        webview.start()
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)
        app.extensions["tinbook_queue"].stop()


if __name__ == "__main__":
    main()