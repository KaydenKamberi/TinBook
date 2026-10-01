"""Tests for core/progress.py owned by CP1C."""

import json
import tempfile
from pathlib import Path

import pytest

from core.models import Progress
from core.progress import load_progress, newer, save_progress


class TestLoadProgress:
    def test_load_existing_progress(self, tmp_path):
        progress_path = tmp_path / "progress.json"
        original = Progress(chapter_index=2, position_sec=30.5, speed=1.5, finished=False, updated_at="2024-01-01T00:00:00Z")
        with open(progress_path, "w", encoding="utf-8") as f:
            json.dump(original.to_dict(), f)

        result = load_progress(tmp_path)
        assert result.chapter_index == 2
        assert result.position_sec == 30.5
        assert result.speed == 1.5
        assert result.finished == False
        assert result.updated_at == "2024-01-01T00:00:00Z"

    def test_load_missing_progress(self, tmp_path):
        result = load_progress(tmp_path)
        assert result == Progress()

    def test_load_corrupt_progress(self, tmp_path):
        progress_path = tmp_path / "progress.json"
        with open(progress_path, "w", encoding="utf-8") as f:
            f.write("not valid json {{{}")

        result = load_progress(tmp_path)
        assert result == Progress()

    def test_load_empty_progress(self, tmp_path):
        progress_path = tmp_path / "progress.json"
        with open(progress_path, "w", encoding="utf-8") as f:
            f.write("")

        result = load_progress(tmp_path)
        assert result == Progress()


class TestSaveProgress:
    def test_save_progress(self, tmp_path):
        progress = Progress(chapter_index=1, position_sec=15.0)
        result = save_progress(tmp_path, progress)

        assert result.updated_at != ""
        assert result.chapter_index == 1
        assert result.position_sec == 15.0

        progress_path = tmp_path / "progress.json"
        assert progress_path.exists()

        with open(progress_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["chapter_index"] == 1
        assert data["position_sec"] == 15.0
        assert data["updated_at"] == result.updated_at

    def test_save_atomic_write(self, tmp_path):
        progress = Progress(chapter_index=1)
        save_progress(tmp_path, progress)

        # The .tmp file should not exist after atomic write
        tmp_file = tmp_path / "progress.json.tmp"
        assert not tmp_file.exists()

    def test_save_returns_copy(self, tmp_path):
        original = Progress(chapter_index=1, updated_at="2024-01-01T00:00:00Z")
        result = save_progress(tmp_path, original)

        # Check that updated_at was changed (since save_progress sets it to now)
        assert result.chapter_index == original.chapter_index
        # The updated_at should be different from the original
        assert result.updated_at != "2024-01-01T00:00:00Z"


class TestNewer:
    def test_newer_by_timestamp(self):
        a = Progress(updated_at="2024-01-01T00:00:00Z")
        b = Progress(updated_at="2024-01-02T00:00:00Z")
        result = newer(a, b)
        assert result == b

    def test_newer_tie_returns_a(self):
        a = Progress(updated_at="2024-01-01T00:00:00Z")
        b = Progress(updated_at="2024-01-01T00:00:00Z")
        result = newer(a, b)
        assert result == a

    def test_empty_timestamp_is_oldest(self):
        a = Progress(updated_at="")
        b = Progress(updated_at="2024-01-01T00:00:00Z")
        result = newer(a, b)
        assert result == b

    def test_both_empty_returns_a(self):
        a = Progress(updated_at="")
        b = Progress(updated_at="")
        result = newer(a, b)
        assert result == a

    def test_b_empty_returns_a(self):
        a = Progress(updated_at="2024-01-01T00:00:00Z")
        b = Progress(updated_at="")
        result = newer(a, b)
        assert result == a

    def test_preserves_all_fields(self):
        a = Progress(chapter_index=1, position_sec=10.0, speed=1.5, finished=True, updated_at="2024-01-02T00:00:00Z")
        b = Progress(chapter_index=2, position_sec=20.0, speed=2.0, finished=False, updated_at="2024-01-01T00:00:00Z")
        result = newer(a, b)
        assert result.chapter_index == 1
        assert result.position_sec == 10.0
        assert result.speed == 1.5
        assert result.finished == True


class TestRoundTrip:
    def test_save_and_load_roundtrip(self, tmp_path):
        original = Progress(
            chapter_index=5,
            position_sec=123.456,
            speed=0.75,
            finished=True,
        )
        saved = save_progress(tmp_path, original)
        loaded = load_progress(tmp_path)

        assert loaded.chapter_index == 5
        assert loaded.position_sec == pytest.approx(123.456)
        assert loaded.speed == 0.75
        assert loaded.finished == True
        assert loaded.updated_at == saved.updated_at
