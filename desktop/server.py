"""Flask HTTP API for Tinbook's desktop client."""

import json
import logging
import math
import threading
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file, url_for
from jinja2 import TemplateNotFound
from werkzeug.exceptions import HTTPException

from core import gutenberg, jobs, library, pipeline, progress, tts
from core.config import get_config
from core.models import Book, Progress

log = logging.getLogger(__name__)
_settings_lock = threading.Lock()


def _body() -> dict:
    data = request.get_json()
    if not isinstance(data, dict):
        abort(400, description="The request body must be a JSON object.")
    return data


def _require_book(book_id: str) -> Book:
    try:
        directory = library.book_dir(book_id)
    except library.LibraryError as error:
        abort(400, description=str(error))
    if not (directory / "book.json").is_file():
        abort(404, description="Book not found.")
    return library.get_book(book_id)


def _audio_path(book: Book, index: int) -> Path:
    path = library.chapter_audio_path(book.id, index, book.audio_format)
    root = library.book_dir(book.id).resolve()
    if not path.resolve().is_relative_to(root):
        abort(404, description="Audio file not found.")
    return path


def _book_view(book: Book) -> dict:
    data = book.to_dict()
    data["progress"] = progress.load_progress(library.book_dir(book.id)).to_dict()
    data["chapters_done"] = book.chapters_done()
    for chapter in data["chapters"]:
        index = chapter["index"]
        chapter["audio_url"] = (
            url_for("chapter_audio", book_id=book.id, index=index)
            if _audio_path(book, index).is_file() else None
        )
    return data


def _updated_progress(book: Book, data: dict) -> Progress:
    allowed = {"chapter_index", "position_sec", "speed", "finished", "updated_at"}
    if data.keys() - allowed:
        abort(400, description="Unknown progress fields.")
    current = progress.load_progress(library.book_dir(book.id)).to_dict()
    current.update({key: value for key, value in data.items() if key != "updated_at"})
    index = current["chapter_index"]
    if type(index) is not int or not 0 <= index < max(1, len(book.chapters)):
        abort(400, description="chapter_index is outside this book.")
    for field in ("position_sec", "speed"):
        value = current[field]
        try:
            finite = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite = False
        if (
            not finite
            or value < 0 or (field == "speed" and value == 0)
        ):
            abort(400, description=f"{field} must be a valid non-negative number; speed must be positive.")
    if not isinstance(current["finished"], bool):
        abort(400, description="finished must be a boolean.")
    return Progress.from_dict(current)


def create_app() -> Flask:
    """Create the HTTP app and start the process-wide generation queue."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        return jsonify(error=error.description), error.code

    @app.errorhandler(pipeline.BookAlreadyExists)
    def duplicate_book(error: pipeline.BookAlreadyExists):
        return jsonify(error=str(error)), 409

    @app.errorhandler(gutenberg.GutenbergError)
    def network_error(error: gutenberg.GutenbergError):
        return jsonify(error=str(error)), 502

    @app.errorhandler(tts.TTSError)
    def invalid_request(error: Exception):
        return jsonify(error=str(error)), 400

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception):
        log.exception("Tinbook request failed")
        return jsonify(error="The request could not be completed. Check the application log."), 500

    @app.get("/")
    def index():
        try:
            return render_template("index.html")
        except TemplateNotFound:
            return jsonify(error="Frontend not installed yet. Merge the CP2B frontend to open Tinbook."), 503

    @app.get("/api/health")
    def health():
        return jsonify(ok=True, env=tts.check_environment())

    @app.get("/api/search")
    def search_books():
        query = request.args.get("q", "").strip()
        if not query:
            abort(400, description="A search query is required.")
        try:
            page = int(request.args.get("page", "1"))
        except ValueError:
            abort(400, description="page must be a positive integer.")
        if page < 1:
            abort(400, description="page must be a positive integer.")
        return jsonify(results=[item.to_dict() for item in gutenberg.search(query, page)])

    @app.get("/api/books")
    def list_books():
        return jsonify(books=[_book_view(book) for book in library.list_books()])

    @app.post("/api/books")
    def add_book():
        data = _body()
        identifier = data.get("gutenberg_id")
        if type(identifier) is not int or identifier <= 0:
            abort(400, description="gutenberg_id must be a positive integer.")
        return jsonify(_book_view(pipeline.add_book(identifier, data.get("voice")))), 201

    @app.get("/api/books/<book_id>")
    def get_book(book_id: str):
        return jsonify(_book_view(_require_book(book_id)))

    @app.delete("/api/books/<book_id>")
    def delete_book(book_id: str):
        _require_book(book_id)
        library.delete_book(book_id)
        return jsonify(ok=True)

    @app.post("/api/books/<book_id>/regenerate")
    def regenerate_book(book_id: str):
        _require_book(book_id)
        data = _body()
        return jsonify(_book_view(pipeline.regenerate_book(book_id, data.get("voice"))))

    @app.get("/api/books/<book_id>/chapters/<int:index>/audio")
    def chapter_audio(book_id: str, index: int):
        book = _require_book(book_id)
        if index >= len(book.chapters):
            abort(404, description="Chapter not found.")
        path = _audio_path(book, index)
        if not path.is_file():
            abort(404, description="Chapter audio has not been generated yet.")
        mimetype = "audio/ogg" if book.audio_format == "opus" else "audio/mpeg"
        return send_file(path, mimetype=mimetype, conditional=True)

    @app.get("/api/books/<book_id>/progress")
    def get_progress(book_id: str):
        book = _require_book(book_id)
        return jsonify(progress.load_progress(library.book_dir(book.id)).to_dict())

    @app.put("/api/books/<book_id>/progress")
    def put_progress(book_id: str):
        book = _require_book(book_id)
        value = _updated_progress(book, _body())
        saved = progress.save_progress(library.book_dir(book.id), value)
        return jsonify(saved.to_dict())

    @app.get("/api/jobs")
    def job_status():
        return jsonify(jobs.get_queue().status())

    @app.get("/api/voices")
    def voices():
        return jsonify(voices=tts.list_voices(), default=get_config().default_voice)

    @app.put("/api/settings")
    def settings():
        voice = _body().get("default_voice")
        if not isinstance(voice, str) or voice not in tts.list_voices():
            abort(400, description="default_voice must name an installed voice.")
        with _settings_lock:
            path = get_config().root_dir / "config.local.json"
            try:
                values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
                if not isinstance(values, dict):
                    raise ValueError("Settings must contain a JSON object")
            except (OSError, ValueError) as error:
                raise OSError("Could not read local settings.") from error
            values["default_voice"] = voice
            library.write_json_atomic(path, values)
            get_config.cache_clear()
        return jsonify(default_voice=voice)

    queue = jobs.get_queue()
    queue.start()
    app.extensions["tinbook_queue"] = queue
    return app