"""Contact sheet rendering and per-frame navigation metadata."""
from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .core import PassSpec, slug_time, stamp


@dataclass(frozen=True)
class FrameRecord:
    index: int
    seconds: float
    timestamp: str
    filename: str
    sheet: str
    cell: int
    row: int
    column: int
    frame_path: str


def font_for(size: int) -> ImageFont.ImageFont:
    candidates = [Path("C:/Windows/Fonts/arialbd.ttf"), Path("C:/Windows/Fonts/seguisb.ttf"),
                  Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                  Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf")]
    for candidate in candidates:
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size)
            except OSError:
                pass
    return ImageFont.load_default()


def overlay(frame: Image.Image, label: str, where: str, font: ImageFont.ImageFont) -> None:
    if where == "none":
        return
    draw = ImageDraw.Draw(frame, "RGBA")
    bounds = draw.textbbox((0, 0), label, font=font)
    w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    px, py = max(4, round(frame.width * 0.012)), max(3, round(frame.height * 0.012))
    margin = max(3, round(frame.width * 0.008))
    x = margin if where.endswith("left") else frame.width - w - 2 * px - margin
    y = margin if where.startswith("top") else frame.height - h - 2 * py - margin
    draw.rounded_rectangle((x, y, x + w + 2 * px, y + h + 2 * py), radius=py, fill=(0, 0, 0, 165))
    draw.text((x + px, y + py - bounds[1]), label, font=font, fill=(255, 255, 255, 255))


def save_sheet(images: list[Path], destination: Path, offset: int, spec: PassSpec,
               times: list[float], *, settings: dict) -> list[FrameRecord]:
    cols, width, gap = settings["columns"], settings["thumb_width"], settings["gap"]
    with Image.open(images[0]) as first:
        height = max(2, round(first.height * width / first.width))
    rows = math.ceil(len(images) / cols)
    canvas = Image.new("RGB", (cols * width + (cols - 1) * gap, rows * height + (rows - 1) * gap), (8, 8, 10))
    font = font_for(max(13, round(width * 0.043)))
    records = []
    for local, src in enumerate(images):
        absolute_index = offset + local
        seconds = spec.start + times[absolute_index]
        row, col = divmod(local, cols)
        with Image.open(src) as stream:
            frame = stream.convert("RGB")
            if frame.size != (width, height):
                frame = frame.resize((width, height), Image.Resampling.LANCZOS)
        label = stamp(seconds)
        if settings["show_frame_number"]:
            label = f"#{absolute_index+1:05d}  {label}"
        overlay(frame, label, settings["timestamp_position"], font)
        canvas.paste(frame, (col * (width + gap), row * (height + gap)))
        records.append(FrameRecord(absolute_index + 1, round(seconds, 6), stamp(seconds),
                                   src.name if settings["keep_frames"] else "", destination.name,
                                   local + 1, row + 1, col + 1,
                                   f"frames/{src.name}" if settings["keep_frames"] else ""))
    fmt = settings["format"]
    options = ({"quality": settings["quality"], "subsampling": 0, "optimize": True} if fmt == "jpg" else
               {"quality": settings["quality"], "method": 6} if fmt == "webp" else
               {"compress_level": 6, "optimize": True})
    canvas.save(destination, **options)
    canvas.close()
    return records


def write_csv(destination: Path, rows: list[FrameRecord]) -> None:
    fieldnames = list(FrameRecord.__dataclass_fields__)
    with destination.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(record) for record in rows)


def build_sheets(frames_dir: Path, sheets_dir: Path, spec: PassSpec, times: list[float],
                 settings: dict) -> tuple[list[FrameRecord], list[dict]]:
    images = sorted(frames_dir.glob("frame_*.jpg"))
    if len(images) != len(times):
        raise RuntimeError("количество файлов кадров не соответствует временным отметкам")
    records: list[FrameRecord] = []
    sheets: list[dict] = []
    batch_size = settings["frames_per_sheet"]
    for number, offset in enumerate(range(0, len(images), batch_size), 1):
        batch = images[offset:offset+batch_size]
        first, last = spec.start + times[offset], spec.start + times[offset+len(batch)-1]
        name = f"sheet_{number:04d}_{slug_time(first)}__{slug_time(last)}.{settings['format']}"
        records.extend(save_sheet(batch, sheets_dir / name, offset, spec, times, settings=settings))
        sheets.append({"sheet": name, "first_frame": offset+1, "last_frame": offset+len(batch),
                       "first_timestamp": stamp(first), "last_timestamp": stamp(last),
                       "first_seconds": round(first, 6), "last_seconds": round(last, 6),
                       "frame_count": len(batch)})
    return records, sheets
