"""Launch Tinbook in a desktop window or browser mode."""

from __future__ import annotations

import argparse
import logging
import threading

from werkzeug.serving import make_server

from .server import create_app

log = logging.getLogger(__name__)

# Always a Promise, so pywebview's callback fires even if the page has no hook yet.
_SAVE_JS = "Promise.resolve(window.tinbook && window.tinbook.saveProgress())"
_SAVE_TIMEOUT_SEC = 2.0


def save_progress_on_close(window, timeout: float = _SAVE_TIMEOUT_SEC) -> None:
    """Make closing the window save playback progress first (PRD D-8).

    pywebview runs ``closing`` handlers on the UI thread, and ``evaluate_js``
    needs that thread, so the handler must not wait for the page. Instead the
    first close is cancelled, a helper thread asks the page to save (waiting at
    most ``timeout`` seconds), then destroys the window; that second close is
    allowed through.
    """
    state = {"saving": False, "closing_for_real": False}

    def save_then_destroy() -> None:
        saved = threading.Event()
        try:
            window.evaluate_js(_SAVE_JS, lambda _result=None: saved.set())
        except Exception as error:  # page gone, JS error: close anyway
            log.warning("Could not save progress before closing: %s", error)
            saved.set()
        if not saved.wait(timeout):
            log.warning("Saving progress took longer than %.0f s; closing anyway", timeout)
        state["closing_for_real"] = True
        window.destroy()

    def on_closing() -> bool:
        if state["closing_for_real"]:
            return True
        if not state["saving"]:
            state["saving"] = True
            threading.Thread(target=save_then_destroy, name="tinbook-close", daemon=True).start()
        return False  # cancel this close; save_then_destroy closes the window

    window.events.closing += on_closing


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
        window = webview.create_window(
            "Tinbook", f"http://127.0.0.1:{server.server_port}",
            width=420, height=720, min_size=(360, 560),
        )
        save_progress_on_close(window)
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