"""FFprobe/FFmpeg access. Does not modify input media."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

from .core import PassSpec, VideoInfo, stamp

SCRIPT_DIR = Path(__file__).resolve().parents[1]
PTS_RE = re.compile(r"\bpts_time:([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")


def resolve_tool(name: str, explicit: Path | None = None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"не найден {name}: {path}")
        return path
    exe = f"{name}.exe" if os.name == "nt" else name
    locations = [SCRIPT_DIR / exe, SCRIPT_DIR / name, SCRIPT_DIR / "tools" / exe,
                 SCRIPT_DIR / "tools" / "ffmpeg" / "bin" / exe, SCRIPT_DIR / "ffmpeg" / "bin" / exe]
    for location in locations:
        if location.is_file():
            return location
    found = shutil.which(name)
    if not found:
        raise FileNotFoundError(f"{name} не найден. Добавьте FFmpeg в PATH либо поместите {exe} рядом со скриптом.")
    return Path(found)


def run(command: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, text=True, capture_output=True, encoding="utf-8",
                              errors="replace", timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"превышено допустимое время работы программы ({timeout:g} с): {Path(command[0]).name}") from exc
    except OSError as exc:
        raise RuntimeError(f"не удалось запустить {Path(command[0]).name}: {exc}") from exc


def version(binary: Path) -> str | None:
    try:
        result = run([str(binary), "-version"], timeout=15)
        return result.stdout.splitlines()[0] if result.returncode == 0 and result.stdout else None
    except RuntimeError:
        return None


def probe(binary: Path, video: Path) -> VideoInfo:
    cmd = [str(binary), "-v", "error", "-show_entries",
           "format=duration,format_name:stream=codec_type,codec_name,width,height,avg_frame_rate,pix_fmt,channels,sample_rate",
           "-of", "json", str(video)]
    result = run(cmd, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "ошибка ffprobe")
    try:
        data = json.loads(result.stdout)
        video_stream = next(x for x in data.get("streams", []) if x.get("codec_type") == "video")
    except (json.JSONDecodeError, StopIteration, KeyError, TypeError) as exc:
        raise RuntimeError("ffprobe не обнаружил читаемый видеопоток") from exc
    audio = next((x for x in data.get("streams", []) if x.get("codec_type") == "audio"), None)
    duration = float((data.get("format") or {}).get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("невозможно определить длительность ролика")
    raw_fps = video_stream.get("avg_frame_rate", "")
    fps = None
    try:
        if "/" in str(raw_fps):
            left, right = map(float, raw_fps.split("/", 1))
            fps = left / right if right else None
        elif raw_fps:
            fps = float(raw_fps)
        if fps is not None and (not math.isfinite(fps) or fps <= 0):
            fps = None
    except (ValueError, ZeroDivisionError):
        fps = None
    return VideoInfo(duration, int(video_stream.get("width") or 0), int(video_stream.get("height") or 0), fps,
                     video_stream.get("codec_name"), video_stream.get("pix_fmt"), bool(audio),
                     audio.get("codec_name") if audio else None,
                     int(audio["channels"]) if audio and audio.get("channels") else None,
                     int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
                     (data.get("format") or {}).get("format_name"), video.stat().st_size)


def extract_samples(ffmpeg: Path, video: Path, directory: Path, spec: PassSpec,
                    width: int, timeout: float) -> list[float]:
    """Select source frames by source PTS, preserve their actual timestamps."""
    interval = spec.interval
    select = f"gte(t,selected_n*{interval:.12g})"
    filters = f"select='{select}',scale={width}:-2:flags=lanczos,showinfo"
    cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "info", "-y", "-ss", f"{spec.start:.6f}",
           "-i", str(video), "-t", f"{spec.duration:.6f}", "-map", "0:v:0", "-an", "-sn", "-dn",
           "-vf", filters, "-q:v", "2", "-fps_mode", "vfr", str(directory / "frame_%07d.jpg")]
    result = run(cmd, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"FFmpeg: ошибка прохода {spec.name}: {result.stderr[-2500:].strip()}")
    times = [float(m.group(1)) for m in PTS_RE.finditer(result.stderr)]
    frames = sorted(directory.glob("frame_*.jpg"))
    if not frames or len(times) < len(frames):
        raise RuntimeError(f"FFmpeg не сформировал корректные кадры или временные отметки: {spec.name}")
    # The image2 muxer may drop the final boundary frame after showinfo has logged it.
    times = times[:len(frames)]
    limit = next((index for index, value in enumerate(times) if value >= spec.duration - 1e-7), len(times))
    for extra in frames[limit:]:
        extra.unlink()
    if not limit:
        raise RuntimeError(f"в диапазоне {stamp(spec.start)}–{stamp(spec.end)} отсутствуют кадры")
    return times[:limit]


def exact_frame(ffmpeg: Path, video: Path, at: float, output: Path, timeout: float) -> None:
    """Fetch a source-resolution frame at / immediately after the requested time."""
    cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-ss", f"{at:.6f}", "-i", str(video), "-map", "0:v:0", "-frames:v", "1", "-an", "-sn", "-dn", str(output)]
    result = run(cmd, timeout=timeout)
    if result.returncode or not output.is_file() or not output.stat().st_size:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"не удалось получить кадр {stamp(at)}: {result.stderr[-1000:].strip()}")
