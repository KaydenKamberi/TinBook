"""Tests for core.tts. Piper and ffmpeg are faked; nothing is really synthesized."""

import io
import json
import shutil
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import tts
from core.config import get_config

RATE = 22050
OPUS_AND_MP3 = " A....D libopus  libopus Opus\n A....D libmp3lame  MP3\n"
MP3_ONLY = " A....D libmp3lame  MP3\n A....D opus  Opus (native, experimental)\n"


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path: Path):
    voices = tmp_path / "voices"
    voices.mkdir()
    monkeypatch.setenv("TINBOOK_VOICES_DIR", str(voices))
    monkeypatch.setenv("TINBOOK_LIBRARY_DIR", str(tmp_path / "library"))
    get_config.cache_clear()
    tts._detect_ffmpeg.cache_clear()
    tts._voice_cache.clear()
    yield voices
    get_config.cache_clear()
    tts._detect_ffmpeg.cache_clear()
    tts._voice_cache.clear()


def install_voice(voices: Path, name: str = "en_US-test-medium") -> str:
    (voices / f"{name}.onnx").write_bytes(b"model")
    (voices / f"{name}.onnx.json").write_text(json.dumps({"audio": {"sample_rate": RATE}}))
    return name


class FakeVoice:
    """Mimics piper.PiperVoice 1.8: synthesize() yields AudioChunk-like objects."""

    loads: list[str] = []

    def __init__(self, samples_per_paragraph: int = RATE, fail: bool = False) -> None:
        self.samples = samples_per_paragraph
        self.fail = fail
        self.calls: list[str] = []

    @classmethod
    def load(cls, model_path: str, config_path: str | None = None) -> "FakeVoice":
        cls.loads.append(model_path)
        return cls()

    def synthesize(self, text: str):
        if self.fail:
            raise RuntimeError("onnx exploded")
        self.calls.append(text)
        yield SimpleNamespace(
            sample_rate=RATE,
            sample_width=2,
            sample_channels=1,
            audio_int16_bytes=b"\x01\x00" * self.samples,
        )


class FakeFFmpeg:
    """Stands in for subprocess.run: answers -encoders and 'encodes' by copying."""

    def __init__(self, encoders: dict[str, str], fail_encode: bool = False) -> None:
        self.encoders = encoders  # ffmpeg path -> -encoders output
        self.fail_encode = fail_encode
        self.encode_commands: list[list[str]] = []

    def __call__(self, command, **kwargs):
        if "-encoders" in command:
            return subprocess.CompletedProcess(command, 0, self.encoders.get(command[0], ""), "")
        self.encode_commands.append(command)
        if self.fail_encode:
            Path(command[-1]).write_bytes(b"half")  # partial output must be cleaned up
            return subprocess.CompletedProcess(command, 1, "", "boom")
        source = Path(command[command.index("-i") + 1])
        shutil.copyfile(source, command[-1])
        return subprocess.CompletedProcess(command, 0, "", "")


@pytest.fixture
def fakes(monkeypatch, env):
    FakeVoice.loads = []
    voice_name = install_voice(env)
    ffmpeg = FakeFFmpeg({"ffmpeg-bundled": OPUS_AND_MP3})
    monkeypatch.setattr(tts, "_ffmpeg_candidates", lambda: ["ffmpeg-bundled"])
    monkeypatch.setattr(tts.subprocess, "run", ffmpeg)
    monkeypatch.setattr(tts, "_piper_voice_class", lambda: FakeVoice)
    return SimpleNamespace(voice=voice_name, ffmpeg=ffmpeg, voices=env)


# ---------------------------------------------------------------- discovery


def test_list_voices_requires_model_and_config(env: Path) -> None:
    install_voice(env, "en_US-b-medium")
    install_voice(env, "en_GB-a-low")
    (env / "en_US-orphan-medium.onnx").write_bytes(b"no json")
    assert tts.list_voices() == ["en_GB-a-low", "en_US-b-medium"]


def test_check_environment_shape(fakes) -> None:
    assert tts.check_environment() == {
        "piper": True,
        "ffmpeg": "ffmpeg-bundled",
        "opus": True,
        "voices": [fakes.voice],
    }


def test_ffmpeg_prefers_candidate_with_libopus(monkeypatch, fakes) -> None:
    monkeypatch.setattr(tts, "_ffmpeg_candidates", lambda: ["bundled", "system"])
    monkeypatch.setattr(tts.subprocess, "run", FakeFFmpeg({"bundled": MP3_ONLY, "system": OPUS_AND_MP3}))
    assert tts._detect_ffmpeg() == ("system", frozenset({"opus", "mp3"}))


def test_ffmpeg_without_libopus_reports_opus_false(monkeypatch, fakes) -> None:
    monkeypatch.setattr(tts.subprocess, "run", FakeFFmpeg({"ffmpeg-bundled": MP3_ONLY}))
    env = tts.check_environment()
    assert env["ffmpeg"] == "ffmpeg-bundled"
    assert env["opus"] is False  # native experimental "opus" encoder doesn't count


def test_ffmpeg_detection_runs_once(monkeypatch, fakes) -> None:
    calls = []
    monkeypatch.setattr(tts, "_encoders", lambda path: calls.append(path) or OPUS_AND_MP3)
    tts.check_environment()
    tts.check_environment()
    assert calls == ["ffmpeg-bundled"]


def test_no_ffmpeg_at_all(monkeypatch, fakes, tmp_path: Path) -> None:
    monkeypatch.setattr(tts, "_ffmpeg_candidates", lambda: [])
    assert tts.check_environment()["ffmpeg"] is None
    with pytest.raises(tts.TTSError, match="ffmpeg not found"):
        tts.synthesize_to_file("Hi.", tmp_path / "a.opus", fakes.voice, "opus", "32k")


# ---------------------------------------------------------------- synthesis


def test_synthesize_writes_file_and_returns_duration(fakes, tmp_path: Path) -> None:
    out = tmp_path / "book" / "audio" / "000.opus"
    duration = tts.synthesize_to_file("Hello there.", out, fakes.voice, "opus", "32k")
    assert duration == pytest.approx(1.0)
    assert out.is_file()
    assert not out.with_name("000.opus.part").exists()
    command = fakes.ffmpeg.encode_commands[0]
    assert command[command.index("-c:a") + 1] == "libopus"
    assert command[command.index("-b:a") + 1] == "32k"
    assert command[command.index("-ac") + 1] == "1"
    assert command[command.index("-f") + 1] == "opus"
    assert command[-1] == str(out) + ".part"


def test_long_text_is_fed_paragraph_by_paragraph(monkeypatch, fakes, tmp_path: Path) -> None:
    voice = FakeVoice()
    monkeypatch.setattr(FakeVoice, "load", classmethod(lambda cls, *a, **k: voice))
    text = "First para\nwrapped line.\n\nSecond para.\n\n  \n\nThird para."
    duration = tts.synthesize_to_file(text, tmp_path / "a.opus", fakes.voice, "opus", "32k")
    assert voice.calls == ["First para wrapped line.", "Second para.", "Third para."]
    # 3 x 1s of speech + 2 paragraph pauses
    assert duration == pytest.approx(3 + 2 * tts._PARAGRAPH_PAUSE_SEC)


def test_voice_is_loaded_once_and_cached(fakes, tmp_path: Path) -> None:
    tts.synthesize_to_file("One.", tmp_path / "1.opus", fakes.voice, "opus", "32k")
    tts.synthesize_to_file("Two.", tmp_path / "2.opus", fakes.voice, "opus", "32k")
    assert len(FakeVoice.loads) == 1


def test_missing_voice_raises(fakes, tmp_path: Path) -> None:
    with pytest.raises(tts.TTSError, match="download_voice.py en_US-nope-medium"):
        tts.synthesize_to_file("Hi.", tmp_path / "a.opus", "en_US-nope-medium", "opus", "32k")


def test_opus_unavailable_raises_helpful_error(monkeypatch, fakes, tmp_path: Path) -> None:
    monkeypatch.setattr(tts.subprocess, "run", FakeFFmpeg({"ffmpeg-bundled": MP3_ONLY}))
    with pytest.raises(tts.TTSError, match='"audio_format": "mp3"'):
        tts.synthesize_to_file("Hi.", tmp_path / "a.opus", fakes.voice, "opus", "32k")


def test_mp3_works_without_opus(monkeypatch, fakes, tmp_path: Path) -> None:
    ffmpeg = FakeFFmpeg({"ffmpeg-bundled": MP3_ONLY})
    monkeypatch.setattr(tts.subprocess, "run", ffmpeg)
    out = tmp_path / "a.mp3"
    tts.synthesize_to_file("Hi.", out, fakes.voice, "mp3", "48k")
    assert out.is_file()
    command = ffmpeg.encode_commands[0]
    assert command[command.index("-c:a") + 1] == "libmp3lame"
    assert command[command.index("-f") + 1] == "mp3"


def test_ffmpeg_failure_leaves_no_partial_file(monkeypatch, fakes, tmp_path: Path) -> None:
    monkeypatch.setattr(tts.subprocess, "run", FakeFFmpeg({"ffmpeg-bundled": OPUS_AND_MP3}, fail_encode=True))
    out = tmp_path / "a.opus"
    with pytest.raises(tts.TTSError, match="ffmpeg failed"):
        tts.synthesize_to_file("Hi.", out, fakes.voice, "opus", "32k")
    assert not out.exists()
    assert not (tmp_path / "a.opus.part").exists()


def test_failed_resynthesis_keeps_previous_complete_file(monkeypatch, fakes, tmp_path: Path) -> None:
    out = tmp_path / "a.opus"
    out.write_bytes(b"old good audio")
    monkeypatch.setattr(tts.subprocess, "run", FakeFFmpeg({"ffmpeg-bundled": OPUS_AND_MP3}, fail_encode=True))
    with pytest.raises(tts.TTSError):
        tts.synthesize_to_file("Hi.", out, fakes.voice, "opus", "32k")
    assert out.read_bytes() == b"old good audio"


def test_piper_exception_is_wrapped_in_tts_error(monkeypatch, fakes, tmp_path: Path) -> None:
    monkeypatch.setattr(FakeVoice, "load", classmethod(lambda cls, *a, **k: FakeVoice(fail=True)))
    with pytest.raises(tts.TTSError, match="onnx exploded"):
        tts.synthesize_to_file("Hi.", tmp_path / "a.opus", fakes.voice, "opus", "32k")
    assert not (tmp_path / "a.opus.part").exists()


@pytest.mark.parametrize(("text", "fmt", "message"), [("Hi.", "flac", "Unsupported"), ("  \n\n ", "opus", "No text")])
def test_bad_input_raises(fakes, tmp_path: Path, text: str, fmt: str, message: str) -> None:
    with pytest.raises(tts.TTSError, match=message):
        tts.synthesize_to_file(text, tmp_path / "a.out", fakes.voice, fmt, "32k")


# ---------------------------------------------------------------- executable fallback


class FakePopen:
    """A 'piper --output_raw' process: emits 0.5s of raw int16 audio per stdin line.

    Like the real thing, stdout only has data after input arrives; read() blocks
    until stdin is closed, which exercises the writer thread in tts.
    """

    instances: list["FakePopen"] = []

    def __init__(self, command, stdin=None, stdout=None, stderr=None) -> None:
        self.command = command
        self.lines: list[str] = []
        self.returncode: int | None = None
        self._closed = threading.Event()
        self._audio = io.BytesIO()
        self.stdin = _StdinRecorder(self)
        self.stdout = self
        FakePopen.instances.append(self)

    def _stdin_closed(self, data: bytes) -> None:
        self.lines = data.decode("utf-8").splitlines()
        self._audio = io.BytesIO(b"\x00\x00" * (RATE // 2) * len(self.lines))
        self._closed.set()

    def read(self, size: int = -1) -> bytes:  # stdout
        assert self._closed.wait(timeout=5), "stdin was never closed"
        return self._audio.read(size)

    def wait(self) -> int:
        self.returncode = 0
        return 0


class _StdinRecorder(io.BytesIO):
    def __init__(self, process: FakePopen) -> None:
        super().__init__()
        self._process = process

    def close(self) -> None:
        if not self.closed:
            self._process._stdin_closed(self.getvalue())
        super().close()


@pytest.fixture
def exe_fallback(monkeypatch, fakes):
    FakePopen.instances = []
    monkeypatch.setattr(tts, "_piper_voice_class", lambda: None)
    monkeypatch.setattr(tts, "_piper_executable", lambda: "/usr/bin/piper")
    monkeypatch.setattr(tts.subprocess, "Popen", FakePopen)
    return fakes


def test_executable_fallback_streams_raw_audio(exe_fallback, tmp_path: Path) -> None:
    out = tmp_path / "a.opus"
    duration = tts.synthesize_to_file("One.\n\nTwo.\n\nThree.", out, exe_fallback.voice, "opus", "32k")
    process = FakePopen.instances[0]
    assert process.command[0] == "/usr/bin/piper"
    assert "--output_raw" in process.command
    assert process.command[process.command.index("--model") + 1].endswith(f"{exe_fallback.voice}.onnx")
    assert process.lines == ["One.", "Two.", "Three."]
    assert duration == pytest.approx(1.5)
    assert out.is_file()
    assert tts.check_environment()["piper"] is True


def test_no_piper_at_all(monkeypatch, fakes, tmp_path: Path) -> None:
    monkeypatch.setattr(tts, "_piper_voice_class", lambda: None)
    monkeypatch.setattr(tts, "_piper_executable", lambda: None)
    assert tts.check_environment()["piper"] is False
    with pytest.raises(tts.TTSError, match="Piper is not available"):
        tts.synthesize_to_file("Hi.", tmp_path / "a.opus", fakes.voice, "opus", "32k")
