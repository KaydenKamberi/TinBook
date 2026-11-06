"""CP2A API, pipeline, and launcher tests with mocked network and queue."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import responses
from jinja2 import DictLoader

from core import config, gutenberg, jobs, library, pipeline, progress, tts
from core.config import get_config
from core.models import SearchResult
from desktop import app as launcher
from desktop.server import create_app


@pytest.fixture(autouse=True)
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_ROOT_DIR", tmp_path)
    for key in ("TINBOOK_LIBRARY_DIR", "TINBOOK_VOICES_DIR", "TINBOOK_DEFAULT_VOICE", "TINBOOK_PORT"):
        monkeypatch.delenv(key, raising=False)
    get_config.cache_clear()
    queue = Mock()
    queue.status.return_value = {"current": None, "queued": []}
    monkeypatch.setattr(jobs, "get_queue", lambda: queue)
    voices_dir = get_config().voices_dir  # tmp_path/voices
    for name in ("en_US-lessac-medium", "en_GB-alba-medium"):  # installed voices (dummy files)
        (voices_dir / f"{name}.onnx").write_bytes(b"model")
        (voices_dir / f"{name}.onnx.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(tts, "check_environment", lambda: {
        "piper": True, "ffmpeg": "ffmpeg", "opus": True, "voices": tts.list_voices(),
    })
    metadata = SearchResult(84, "Frankenstein", ["Shelley, Mary"], "en", 10, "https://example.org/84.txt")
    raw = (
        "*** START OF THE PROJECT GUTENBERG EBOOK FRANKENSTEIN ***\n\n"
        "CHAPTER I\n\n" + "First chapter words. " * 80
        + "\n\nCHAPTER II\n\n" + "Second chapter words. " * 80
        + "\n\n*** END OF THE PROJECT GUTENBERG EBOOK FRANKENSTEIN ***"
    )
    monkeypatch.setattr(gutenberg, "get_metadata", Mock(return_value=metadata))
    monkeypatch.setattr(gutenberg, "download_text", Mock(return_value=raw))
    monkeypatch.setattr(gutenberg, "search", Mock(return_value=[metadata]))
    with responses.RequestsMock():
        yield SimpleNamespace(queue=queue, metadata=metadata, raw=raw, root=tmp_path)
    get_config.cache_clear()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def book(client):
    result = client.post("/api/books", json={"gutenberg_id": 84})
    assert result.status_code == 201
    return library.get_book(result.json["id"])


def test_app_starts_queue_once_and_health_reports_environment(app, client, sandbox):
    sandbox.queue.start.assert_called_once_with()
    assert app.extensions["tinbook_queue"] is sandbox.queue
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json["ok"] is True
    assert response.json["env"]["opus"] is True


def test_root_serves_frontend_without_requiring_frontend_files_in_this_branch(app, client):
    app.jinja_loader = DictLoader({"index.html": "<title>Tinbook test template</title>"})
    assert b"Tinbook test template" in client.get("/").data


def test_missing_frontend_is_explicit_json_503(app, client):
    app.jinja_loader = DictLoader({})
    response = client.get("/")
    assert response.status_code == 503
    assert "CP2B" in response.json["error"]


def test_static_assets_are_served(app, client, tmp_path):
    assets = tmp_path / "static"
    assets.mkdir()
    (assets / "app.js").write_text("/* test asset */", encoding="utf-8")
    app.static_folder = str(assets)
    assert client.get("/static/app.js").data == b"/* test asset */"


def test_search_returns_serialized_results_and_page(client, sandbox):
    response = client.get("/api/search?q=frankenstein&page=2")
    assert response.status_code == 200
    assert response.json == {"results": [sandbox.metadata.to_dict()]}
    gutenberg.search.assert_called_once_with("frankenstein", 2)


@pytest.mark.parametrize("query", ["", "?q=", "?q=x&page=0", "?q=x&page=-1", "?q=x&page=no"])
def test_invalid_search_is_json_400(client, query):
    response = client.get("/api/search" + query)
    assert response.status_code == 400
    assert response.json["error"]


def test_search_transport_failure_is_json_502(client):
    gutenberg.search.side_effect = gutenberg.GutenbergError("Service unavailable")
    response = client.get("/api/search?q=frankenstein")
    assert response.status_code == 502
    assert response.json == {"error": "Service unavailable"}


def test_add_runs_real_clean_split_storage_and_enqueues(client, sandbox):
    response = client.post("/api/books", json={"gutenberg_id": 84, "voice": None})
    assert response.status_code == 201
    data = response.json
    assert data["status"] == "queued"
    assert data["voice"] == "piper:" + get_config().default_voice  # stored canonical (CP3)
    assert len(data["chapters"]) == 2
    assert all(chapter["status"] == "pending" for chapter in data["chapters"])
    assert all(chapter["audio_url"] is None for chapter in data["chapters"])
    assert data["chapters_done"] == 0
    assert data["progress"]["position_sec"] == 0
    text = library.chapter_text_path(data["id"], 0).read_text(encoding="utf-8")
    assert "First chapter words." in text
    assert "*** START OF" not in text
    assert (library.book_dir(data["id"]) / "raw.txt").read_text(encoding="utf-8") == sandbox.raw
    sandbox.queue.enqueue.assert_called_once_with(data["id"])


def test_explicit_voice_is_used(client):
    response = client.post("/api/books", json={"gutenberg_id": 84, "voice": "en_GB-alba-medium"})
    assert response.status_code == 201
    assert response.json["voice"] == "piper:en_GB-alba-medium"  # stored canonical (CP3)


@pytest.mark.parametrize("data", [{}, {"gutenberg_id": True}, {"gutenberg_id": 0},
    {"gutenberg_id": "84"}, {"gutenberg_id": -1}, [], None])
def test_invalid_add_body_is_json_400(client, data):
    response = client.post("/api/books", data=json.dumps(data), content_type="application/json")
    assert response.status_code == 400
    assert response.json["error"]


def test_non_json_and_malformed_json_return_json_errors(client):
    assert client.post("/api/books", data="text").status_code == 415
    response = client.post("/api/books", data="{", content_type="application/json")
    assert response.status_code == 400
    assert response.json["error"]


def test_duplicate_book_is_409_and_original_is_preserved(client, book):
    response = client.post("/api/books", json={"gutenberg_id": 84})
    assert response.status_code == 409
    assert library.get_book(book.id) == book


def test_simultaneous_duplicate_add_is_409_not_500(client, book, monkeypatch):
    """CP3: the add that loses a create race gets 409, like any other duplicate."""
    real_book_dir = library.book_dir
    hidden = {"yes": True}

    def book_dir_hiding_existing(book_id):
        # The pre-check runs before the other add finished: pretend the folder is absent.
        path = real_book_dir(book_id)
        if hidden["yes"]:
            hidden["yes"] = False
            return path.parent / f"not-yet-{book_id}"
        return path

    monkeypatch.setattr(pipeline.library, "book_dir", book_dir_hiding_existing)
    response = client.post("/api/books", json={"gutenberg_id": 84})
    assert response.status_code == 409
    assert "already exists" in response.json["error"]
    assert library.get_book(book.id) == book


@pytest.mark.parametrize("voice", ["not-installed", "", False, []])
def test_invalid_voice_does_not_download_or_create_book(client, voice, sandbox):
    response = client.post("/api/books", json={"gutenberg_id": 84, "voice": voice})
    assert response.status_code == 400
    gutenberg.download_text.assert_not_called()
    sandbox.queue.enqueue.assert_not_called()
    assert library.list_books() == []


def test_download_failure_creates_no_book(client, sandbox):
    gutenberg.download_text.side_effect = gutenberg.GutenbergError("Download unavailable")
    assert client.post("/api/books", json={"gutenberg_id": 84}).status_code == 502
    assert library.list_books() == []
    sandbox.queue.enqueue.assert_not_called()


def test_books_list_detail_and_playable_audio_urls(client, book):
    assert client.get("/api/books").json["books"][0]["id"] == book.id
    path = library.chapter_audio_path(book.id, 0, "opus")
    path.write_bytes(b"OggS" + bytes(range(256)))
    book.chapters[0].status = "done"
    book.chapters[0].duration_sec = 1.2
    library.save_book(book)
    view = client.get(f"/api/books/{book.id}").json
    assert view["chapters_done"] == 1
    assert view["chapters"][0]["audio_url"].endswith("/chapters/0/audio")
    assert view["chapters"][1]["audio_url"] is None


def test_audio_full_range_and_unsatisfiable_range(client, book):
    data = b"OggS" + bytes(range(256))
    library.chapter_audio_path(book.id, 0, "opus").write_bytes(data)
    url = f"/api/books/{book.id}/chapters/0/audio"
    full = client.get(url)
    assert full.status_code == 200
    assert full.mimetype == "audio/ogg"
    assert full.data == data
    partial = client.get(url, headers={"Range": "bytes=0-100"})
    assert partial.status_code == 206
    assert partial.data == data[:101]
    assert partial.headers["Content-Range"] == f"bytes 0-100/{len(data)}"
    invalid = client.get(url, headers={"Range": "bytes=9999-10000"})
    assert invalid.status_code == 416
    assert invalid.json["error"]


def test_mp3_content_type(client, book):
    book.audio_format = "mp3"
    library.save_book(book)
    library.chapter_audio_path(book.id, 0, "mp3").write_bytes(b"ID3audio")
    assert client.get(f"/api/books/{book.id}/chapters/0/audio").mimetype == "audio/mpeg"


@pytest.mark.parametrize("index", [0, 99, -1])
def test_missing_or_invalid_chapter_audio_is_json_404(client, book, index):
    response = client.get(f"/api/books/{book.id}/chapters/{index}/audio")
    assert response.status_code == 404
    assert response.json["error"]


def test_audio_symlink_cannot_expose_external_file(client, book, tmp_path):
    outside = tmp_path / "private.txt"
    outside.write_text("private", encoding="utf-8")
    try:
        library.chapter_audio_path(book.id, 0, "opus").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks not available")
    assert client.get(f"/api/books/{book.id}/chapters/0/audio").status_code == 404


def test_progress_get_put_and_partial_update(client, book):
    url = f"/api/books/{book.id}/progress"
    assert client.get(url).json["updated_at"] == ""
    saved = client.put(url, json={"chapter_index": 1, "position_sec": 12.5, "speed": 1.5}).json
    assert saved["chapter_index"] == 1
    assert saved["position_sec"] == 12.5
    assert saved["updated_at"].endswith("Z")
    partial = client.put(url, json={"finished": True, "updated_at": "spoofed"}).json
    assert partial["position_sec"] == 12.5
    assert partial["speed"] == 1.5
    assert partial["finished"] is True
    assert partial["updated_at"] != "spoofed"
    assert client.get(url).json == partial


@pytest.mark.parametrize("data", [
    {"chapter_index": -1}, {"chapter_index": 100}, {"chapter_index": True},
    {"position_sec": -1}, {"position_sec": "12"}, {"position_sec": float("inf")},
    {"speed": 0}, {"speed": -1}, {"speed": True}, {"speed": float("nan")},
    {"finished": "yes"}, {"unknown": 1},
])
def test_invalid_progress_does_not_write(client, book, data):
    response = client.put(f"/api/books/{book.id}/progress", json=data)
    assert response.status_code == 400
    assert not (library.book_dir(book.id) / "progress.json").exists()


def test_regeneration_resets_audio_metadata_and_preserves_progress(client, book, sandbox):
    book.status = "error"
    book.error = "Old error"
    for chapter in book.chapters:
        chapter.status = "done"
        chapter.duration_sec = 12
        library.chapter_audio_path(book.id, chapter.index, book.audio_format).write_bytes(b"old")
    library.save_book(book)
    progress.save_progress(library.book_dir(book.id), progress.Progress(position_sec=5))
    sandbox.queue.enqueue.reset_mock()
    response = client.post(f"/api/books/{book.id}/regenerate", json={"voice": "en_GB-alba-medium"})
    assert response.status_code == 200
    assert response.json["status"] == "queued"
    assert response.json["error"] is None
    assert response.json["voice"] == "piper:en_GB-alba-medium"
    assert response.json["progress"]["position_sec"] == 5
    assert all(chapter["status"] == "pending" for chapter in response.json["chapters"])
    assert all(chapter["duration_sec"] is None for chapter in response.json["chapters"])
    assert list((library.book_dir(book.id) / "audio").iterdir()) == []
    assert library.chapter_text_path(book.id, 0).exists()
    sandbox.queue.enqueue.assert_called_once_with(book.id)


def test_regeneration_switches_book_to_configured_audio_format(client, book):
    """CP3: regenerate re-encodes in the configured audio_format (here mp3 -> opus)."""
    book.audio_format = "mp3"
    book.status = "error"
    library.save_book(book)
    response = client.post(f"/api/books/{book.id}/regenerate", json={"voice": "en_US-lessac-medium"})
    assert response.status_code == 200
    assert response.json["audio_format"] == get_config().audio_format == "opus"
    assert response.json["status"] == "queued"


def test_invalid_regeneration_keeps_audio(client, book):
    path = library.chapter_audio_path(book.id, 0, book.audio_format)
    path.write_bytes(b"keep")
    response = client.post(f"/api/books/{book.id}/regenerate", json={"voice": "missing"})
    assert response.status_code == 400
    assert path.read_bytes() == b"keep"
    assert library.get_book(book.id) == book


def test_delete_while_queued_only_deletes_book(client, book, sandbox):
    sandbox.queue.reset_mock()
    response = client.delete(f"/api/books/{book.id}")
    assert response.json == {"ok": True}
    assert not library.book_dir(book.id).exists()
    sandbox.queue.stop.assert_not_called()
    sandbox.queue.enqueue.assert_not_called()


@pytest.mark.parametrize("method, suffix", [
    ("get", ""), ("delete", ""), ("post", "/regenerate"),
    ("get", "/progress"), ("put", "/progress"), ("get", "/chapters/0/audio"),
])
def test_missing_books_return_json_404(client, method, suffix):
    response = getattr(client, method)("/api/books/missing" + suffix, json={})
    assert response.status_code == 404
    assert response.json["error"]


def test_jobs_and_voices(client, sandbox):
    sandbox.queue.status.return_value = {"current": {"book_id": "x"}, "queued": ["y"]}
    assert client.get("/api/jobs").json == sandbox.queue.status.return_value
    assert client.get("/api/voices").json == {  # canonical IDs since CP3
        "voices": ["piper:en_GB-alba-medium", "piper:en_US-lessac-medium"],
        "default": "piper:en_US-lessac-medium",
    }


def test_settings_atomic_persistence_preserves_other_settings_and_clears_cache(client, sandbox):
    path = sandbox.root / "config.local.json"
    library.write_json_atomic(path, {"audio_bitrate": "48k"})
    get_config.cache_clear()
    response = client.put("/api/settings", json={"default_voice": "en_GB-alba-medium"})
    assert response.status_code == 200
    assert response.json == {"default_voice": "piper:en_GB-alba-medium"}  # stored canonical (CP3)
    assert get_config().default_voice == "piper:en_GB-alba-medium"
    assert get_config().audio_bitrate == "48k"
    assert not path.with_name(path.name + ".tmp").exists()
    assert json.loads(path.read_text(encoding="utf-8"))["audio_bitrate"] == "48k"


def test_settings_rejects_missing_voice(client, sandbox):
    assert client.put("/api/settings", json={"default_voice": "missing"}).status_code == 400
    assert not (sandbox.root / "config.local.json").exists()


def test_corrupt_settings_and_storage_failure_are_json_500(client, sandbox, monkeypatch):
    (sandbox.root / "config.local.json").write_text("[]", encoding="utf-8")
    assert client.put("/api/settings", json={"default_voice": "en_GB-alba-medium"}).status_code == 500
    monkeypatch.setattr(library, "list_books", Mock(side_effect=library.LibraryError("Disk failed")))
    response = client.get("/api/books")
    assert response.status_code == 500
    assert response.json["error"]


def test_unknown_routes_methods_and_oversized_body_return_json(client):
    assert client.get("/api/no-such-route").status_code == 404
    assert client.patch("/api/books").status_code == 405
    response = client.post("/api/books", data=" " * 70000, content_type="application/json")
    assert response.status_code == 413
    assert response.json["error"]


def test_pipeline_rejects_invalid_id_without_network(sandbox):
    with pytest.raises(ValueError):
        pipeline.add_book(True)
    gutenberg.get_metadata.assert_not_called()


def test_browser_launcher_uses_expected_binding_and_stops_queue(monkeypatch, app, sandbox):
    monkeypatch.setattr(launcher, "create_app", lambda: app)
    run = Mock()
    monkeypatch.setattr(app, "run", run)
    monkeypatch.setattr(sys, "argv", ["tinbook", "--browser"])
    launcher.main()
    run.assert_called_once_with(host="0.0.0.0", port=5000, use_reloader=False, threaded=True)
    sandbox.queue.stop.assert_called_once_with()


@pytest.mark.parametrize("webview_fails", [False, True])
def test_desktop_launcher_dimensions_binding_and_shutdown(monkeypatch, app, sandbox, webview_fails):
    monkeypatch.setattr(launcher, "create_app", lambda: app)
    monkeypatch.setattr(sys, "argv", ["tinbook"])
    server = Mock(server_port=54321)
    make_server = Mock(return_value=server)
    monkeypatch.setattr(launcher, "make_server", make_server)
    thread = Mock()
    make_thread = Mock(return_value=thread)
    monkeypatch.setattr(launcher.threading, "Thread", make_thread)
    window = Mock()
    close_hook = Mock()
    monkeypatch.setattr(launcher, "save_progress_on_close", close_hook)
    webview = SimpleNamespace(create_window=Mock(return_value=window), start=Mock())
    if webview_fails:
        webview.start.side_effect = RuntimeError("Window closed unexpectedly")
    monkeypatch.setitem(sys.modules, "webview", webview)
    if webview_fails:
        with pytest.raises(RuntimeError):
            launcher.main()
    else:
        launcher.main()
    make_server.assert_called_once_with("127.0.0.1", 0, app, threaded=True)
    make_thread.assert_called_once_with(target=server.serve_forever, daemon=True)
    webview.create_window.assert_called_once_with(
        "Tinbook", "http://127.0.0.1:54321", width=420, height=720, min_size=(360, 560),
    )
    thread.start.assert_called_once_with()
    close_hook.assert_called_once_with(window)  # close hook installed (CP3)
    server.shutdown.assert_called_once_with()
    server.server_close.assert_called_once_with()
    sandbox.queue.stop.assert_called_once_with()


class FakeEvent:
    """Minimal pywebview Event: ``+=`` adds a handler; ``fire`` returns False if any handler did."""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self):
        return all(handler() is not False for handler in self.handlers)


class FakeWindow:
    def __init__(self, resolve=True, raise_on_eval=False):
        self.events = SimpleNamespace(closing=FakeEvent())
        self.resolve = resolve
        self.raise_on_eval = raise_on_eval
        self.scripts = []
        self.destroyed = launcher.threading.Event()

    def evaluate_js(self, script, callback=None):
        self.scripts.append(script)
        if self.raise_on_eval:
            raise RuntimeError("page is gone")
        if self.resolve:
            callback(True)

    def destroy(self):
        self.destroyed.set()


@pytest.mark.parametrize("window_kwargs", [{}, {"resolve": False}, {"raise_on_eval": True}])
def test_close_saves_progress_then_destroys_window(window_kwargs):
    """CP3 / PRD D-8: first close is cancelled, the page saves, then the window closes."""
    window = FakeWindow(**window_kwargs)
    launcher.save_progress_on_close(window, timeout=0.2)
    assert window.events.closing.fire() is False  # first close: cancelled while saving
    assert window.destroyed.wait(2)
    assert window.scripts == [launcher._SAVE_JS]
    assert "window.tinbook.saveProgress()" in launcher._SAVE_JS
    assert window.events.closing.fire() is True  # the close from destroy() goes through


def test_repeated_close_clicks_start_only_one_save():
    window = FakeWindow(resolve=False)
    launcher.save_progress_on_close(window, timeout=0.3)
    assert window.events.closing.fire() is False
    assert window.events.closing.fire() is False
    assert window.destroyed.wait(2)
    assert window.scripts == [launcher._SAVE_JS]

