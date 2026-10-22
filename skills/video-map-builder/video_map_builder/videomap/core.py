"""Shared data types, timestamp helpers, validation and safe JSON writing."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float | None
    video_codec: str | None
    pixel_format: str | None
    audio_present: bool
    audio_codec: str | None
    audio_channels: int | None
    audio_sample_rate: int | None
    format_name: str | None
    file_size: int


@dataclass(frozen=True)
class PassSpec:
    name: str
    start: float
    end: float
    fps: float
    kind: str

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def interval(self) -> float:
        return 1.0 / self.fps

    def to_dict(self) -> dict:
        return {**asdict(self), "duration": self.duration, "interval": self.interval}


def number(value: str, *, allow_zero: bool = False) -> float:
    try:
        result = float(value.replace(",", "."))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ожидалось число") from exc
    if not math.isfinite(result) or result < 0 or (not allow_zero and result == 0):
        raise argparse.ArgumentTypeError("ожидалось конечное положительное число" if not allow_zero else "число должно быть неотрицательным")
    return result


def positive_float(value: str) -> float:
    return number(value)


def nonnegative_float(value: str) -> float:
    return number(value, allow_zero=True)


def positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ожидалось целое число") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("ожидалось положительное целое число")
    return result


def nonnegative_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ожидалось целое число") from exc
    if result < 0:
        raise argparse.ArgumentTypeError("число не может быть отрицательным")
    return result


def parse_timecode(value: str) -> float:
    """Seconds, MM:SS[.mmm], HH:MM:SS[.mmm], commas allowed."""
    raw = value.strip().replace(",", ".")
    parts = raw.split(":")
    if not 1 <= len(parts) <= 3 or not all(re.fullmatch(r"\d+(?:\.\d+)?", p) for p in parts):
        raise ValueError(f"неверный таймкод: {value!r}")
    if len(parts) > 1:
        if not all(p.isdigit() for p in parts[:-1]) or float(parts[-1]) >= 60:
            raise ValueError(f"неверный таймкод: {value!r}")
        if len(parts) == 3 and int(parts[1]) >= 60:
            raise ValueError(f"неверный таймкод: {value!r}")
    result = sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))
    if not math.isfinite(result):
        raise ValueError(f"неверный таймкод: {value!r}")
    return result


def time_argument(value: str) -> float:
    try:
        return parse_timecode(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def stamp(seconds: float, *, milliseconds: bool = True) -> str:
    ticks = max(0, round(seconds * 1000))
    h, ticks = divmod(ticks, 3600000)
    m, ticks = divmod(ticks, 60000)
    s, ms = divmod(ticks, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}" + (f".{ms:03d}" if milliseconds else "")


def slug_time(seconds: float) -> str:
    return stamp(seconds).replace(":", "-").replace(".", "_")


def rate_label(fps: float) -> str:
    if abs(fps - round(fps)) < 1e-9:
        return f"{round(fps)}fps"
    return f"{fps:.6f}".rstrip("0").rstrip(".").replace(".", "_") + "fps"


def parse_detail(raw: str, duration: float, ordinal: int, prefix: str = "detail") -> PassSpec:
    match = re.fullmatch(r"\s*(.+?)\s*-\s*(.+?)\s*@\s*([0-9]+(?:[.,][0-9]+)?)\s*", raw)
    if not match:
        raise ValueError(f"неверный диапазон {raw!r}; пример: 12:52-14:22@5")
    start, end = parse_timecode(match.group(1)), parse_timecode(match.group(2))
    fps = positive_float(match.group(3))
    if start >= duration or end <= start or end > duration + 0.001:
        raise ValueError(f"диапазон {raw!r} выходит за пределы ролика или имеет нулевую длину")
    end = min(end, duration)
    return PassSpec(f"{prefix}_{ordinal:02d}_{slug_time(start)}__{slug_time(end)}_{rate_label(fps)}", start, end, fps, "detail")


def signature(path: Path) -> dict:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def atomic_json(path: Path, payload: dict) -> None:
    """Commit JSON by replacing the destination only after a complete write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".manifest_", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("ожидался объект JSON")
        return data
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"не удалось прочитать {path}: {exc}") from exc


def project_path(project: Path, relative: str) -> Path:
    """Disallow paths inside metadata that escape the project directory."""
    destination = (project / relative).resolve()
    if not destination.is_relative_to(project.resolve()):
        raise ValueError("путь в описании проекта выходит за его пределы")
    return destination
