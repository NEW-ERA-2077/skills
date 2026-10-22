"""Resumable projects, cache validation, lookup and high-resolution extraction."""
from __future__ import annotations

import csv
import math
import shutil
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .core import PassSpec, VideoInfo, atomic_json, parse_detail, project_path, rate_label, read_json, signature, slug_time, stamp
from .media import exact_frame, extract_samples, probe, version
from .sheets import build_sheets, write_csv

DEFAULTS = {"frames_per_sheet": 25, "columns": 5, "thumb_width": 320,
            "gap": 2, "format": "jpg", "quality": 90, "timestamp_position": "top-left",
            "show_frame_number": False, "keep_frames": False}


def video_path(manifest: dict, project: Path) -> Path:
    path = Path(manifest["source"]["path"]).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"исходное видео больше не найдено: {path}")
    source = manifest["source"]
    old = source.get("signature")
    if old is not None and signature(path) != old:
        raise ValueError("исходное видео изменено: размер или дата модификации не совпадают с картой")
    if old is None and path.stat().st_size != source.get("file_size"):
        raise ValueError("исходное видео отличается от использованного для карты")
    return path


def load_project(project: Path) -> dict:
    return read_json(project / "manifest.json")


def create_manifest(video: Path, info: VideoInfo, specs: list[PassSpec], settings: dict,
                    ffmpeg: Path, ffprobe: Path) -> dict:
    return {"schema_version": 2, "status": "incomplete",
            "source": {"path": str(video), "name": video.name, **asdict(info), "signature": signature(video)},
            "settings": settings, "passes": [spec.to_dict() for spec in specs], "results": [],
            "tools": {"ffmpeg": str(ffmpeg), "ffmpeg_version": version(ffmpeg),
                      "ffprobe": str(ffprobe), "ffprobe_version": version(ffprobe),
                      "python": sys.version.split()[0]},
            "elapsed_seconds": 0.0, "updated_utc": datetime.now(timezone.utc).isoformat()}


def save_manifest(project: Path, manifest: dict) -> None:
    manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
    atomic_json(project / "manifest.json", manifest)


def verify_pass(project: Path, name: str, settings: dict, result: dict | None = None) -> bool:
    folder = project_path(project, name)
    csv_file = folder / "frames.csv"
    if not csv_file.is_file() or not (folder / "INFO.txt").is_file():
        return False
    try:
        with csv_file.open(encoding="utf-8-sig", newline="") as source:
            frames = list(csv.DictReader(source))
        if not frames:
            return False
        sheets = {r["sheet"] for r in frames}
        if not all((folder / "sheets" / name).is_file() for name in sheets):
            return False
        if settings["keep_frames"]:
            if not all((folder / "frames" / r["filename"]).is_file() for r in frames):
                return False
        if result and (len(frames) != result.get("frame_count") or len(sheets) != result.get("sheet_count")):
            return False
        return True
    except (OSError, KeyError, ValueError):
        return False


def process_pass(project: Path, video: Path, ffmpeg: Path, spec: PassSpec,
                 settings: dict, timeout: float, log) -> dict:
    final = project_path(project, spec.name)
    if final.exists():
        raise FileExistsError(f"папка прохода уже существует: {final}")
    work = project / (".working_" + spec.name)
    if work.exists():
        shutil.rmtree(work)  # only temporary directories owned by this script
    work.mkdir(parents=True)
    sheets_dir = work / "sheets"
    sheets_dir.mkdir()
    frames_dir = work / ("frames" if settings["keep_frames"] else "_tmp_frames")
    frames_dir.mkdir()
    try:
        log(f"[{spec.name}] {stamp(spec.start)}–{stamp(spec.end)}; {spec.fps:g} кадра/с")
        times = extract_samples(ffmpeg, video, frames_dir, spec, settings["thumb_width"], timeout)
        records, sheets = build_sheets(frames_dir, sheets_dir, spec, times, settings)
        write_csv(work / "frames.csv", records)
        (work / "INFO.txt").write_text(
            f"Проход: {spec.name}\nТип: {spec.kind}\nНачало: {stamp(spec.start)}\n"
            f"Конец: {stamp(spec.end)}\nЧастота: {spec.fps:g} кадров/с\n"
            f"Кадров: {len(records)}\nЛистов: {len(sheets)}\n"
            f"Отдельные кадры: {'да' if settings['keep_frames'] else 'нет'}\n"
            "См. frames.csv для координат кадров на контакт-листах.\n", encoding="utf-8")
        if not settings["keep_frames"]:
            shutil.rmtree(frames_dir)
        result = {"name": spec.name, "directory": spec.name,
                  "frame_count": len(records), "sheet_count": len(sheets), "sheets": sheets}
        atomic_json(work / "pass.json", {"spec": spec.to_dict(), "result": result})
        work.rename(final)
        return result
    except Exception:
        # Work directory survives for diagnosis, never marks the pass as ready.
        raise


def root_readme(project: Path, manifest: dict) -> None:
    src = manifest["source"]
    lines = ["КАРТА ВИДЕО", "============", "", f"Исходник: {src['path']}",
             f"Длительность: {stamp(src['duration'])}",
             f"Разрешение: {src['width']}x{src['height']}", "", "ПРОХОДЫ"]
    for item in manifest["passes"]:
        lines.append(f"- {item['name']}: {stamp(item['start'])}–{stamp(item['end'])} ({item['fps']:g} кадра/с)")
    lines += ["", "НАВИГАЦИЯ", "1. Откройте обзорные листы в папке 01_overview_*.",
              "2. Изучите основную карту 02_main_*.",
              "3. Для детализации используйте проходы hook/detail/extra.",
              "4. В frames.csv указаны таймкод, лист, номер строки и колонки.",
              "5. Команда locate находит кадры между двумя таймкодами.",
              "", "Исходный видеоролик не изменён."]
    (project / "README_MAP.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def execute(project: Path, video: Path, ffmpeg: Path, manifest: dict, specs: list[PassSpec],
            timeout: float, log) -> dict:
    started = time.monotonic()
    settings = manifest["settings"]
    results = {r["name"]: r for r in manifest.get("results", [])}
    manifest["status"] = "incomplete"
    save_manifest(project, manifest)
    for spec in specs:
        result = results.get(spec.name)
        if result and verify_pass(project, spec.name, settings, result):
            log(f"[{spec.name}] уже готов, пропускаю")
            continue
        final = project_path(project, spec.name)
        if final.exists():
            # Recover a completed pass after a crash between atomic directory
            # rename and the next manifest update.
            record = final / "pass.json"
            if record.is_file():
                payload = read_json(record)
                recovered = payload.get("result")
                if payload.get("spec") == spec.to_dict() and recovered and verify_pass(project, spec.name, settings, recovered):
                    log(f"[{spec.name}] восстановлен из сохранённых файлов")
                    results[spec.name] = recovered
                    manifest["results"] = [results[p["name"]] for p in manifest["passes"] if p["name"] in results]
                    save_manifest(project, manifest)
                    continue
            raise RuntimeError(f"проход {spec.name} повреждён или неполон: {final}. Проверьте папку перед ручным удалением.")
        result = process_pass(project, video, ffmpeg, spec, settings, timeout, log)
        results[spec.name] = result
        manifest["results"] = [results[p["name"]] for p in manifest["passes"] if p["name"] in results]
        save_manifest(project, manifest)
    # A completed manifest must not conceal an unfinished earlier pass.
    missing = [p["name"] for p in manifest["passes"] if p["name"] not in results
               or not verify_pass(project, p["name"], settings, results[p["name"]])]
    if missing:
        raise RuntimeError(f"в проекте есть незавершённые проходы: {', '.join(missing)}")
    manifest["status"] = "complete"
    manifest["elapsed_seconds"] = round(manifest.get("elapsed_seconds", 0) + time.monotonic()-started, 3)
    save_manifest(project, manifest)
    root_readme(project, manifest)
    (project / "INCOMPLETE.txt").unlink(missing_ok=True)
    return summary(project, manifest)


def summary(project: Path, manifest: dict) -> dict:
    return {"ok": manifest.get("status") == "complete", "project": str(project),
            "manifest": str(project / "manifest.json"), "status": manifest.get("status", "unknown"),
            "passes": len(manifest.get("results", [])),
            "frames": sum(int(r["frame_count"]) for r in manifest.get("results", [])),
            "sheets": sum(int(r["sheet_count"]) for r in manifest.get("results", []))}


def build_specs(args, info: VideoInfo) -> list[PassSpec]:
    duration = info.duration
    if args.fps is not None or args.interval is not None:
        fps = args.fps if args.fps is not None else 1 / args.interval
        start = args.start
        end = args.end if args.end is not None else (start + args.duration if args.duration is not None else duration)
        if start >= duration or end <= start or end > duration + 0.001:
            raise ValueError("неверный диапазон --start/--end: конец должен быть позже начала и не позже конца видео")
        specs = [PassSpec(f"map_{rate_label(fps)}", start, min(end, duration), fps, "uniform")]
    else:
        if args.start != 0 or args.end is not None or args.duration is not None:
            raise ValueError("--start/--end/--duration требуют --fps либо --interval")
        specs = []
        if not args.no_overview:
            specs.append(PassSpec(f"01_overview_every_{args.overview_interval:g}s".replace(".", "_"),
                                  0, duration, 1 / args.overview_interval, "overview"))
        specs.append(PassSpec(f"02_main_{rate_label(args.main_fps)}", 0, duration, args.main_fps, "main"))
        if not args.no_hook and args.hook_seconds > 0:
            secs = min(duration, args.hook_seconds)
            specs.append(PassSpec(f"03_hook_first_{args.hook_seconds:g}s_{rate_label(args.hook_fps)}".replace(".", "_"),
                                  0, secs, args.hook_fps, "hook"))
    for index, raw in enumerate(args.detail or [], 1):
        specs.append(parse_detail(raw, duration, index))
    for spec in specs:
        check_fps(spec, info)
    if len({s.name for s in specs}) != len(specs):
        raise ValueError("папки проходов должны иметь уникальные имена")
    return specs


def check_fps(spec: PassSpec, info: VideoInfo) -> None:
    if info.fps and spec.fps > info.fps * 1.05:
        raise ValueError(f"{spec.name}: запрошено {spec.fps:g} кадров/с, а в видео около {info.fps:g}")


def estimate(specs: list[PassSpec], settings: dict) -> dict:
    items = []
    for s in specs:
        # Upper approximation for videos with known frame rate; actual depends on source PTS.
        frames = math.ceil(s.duration * s.fps)
        items.append({"name": s.name, "from": stamp(s.start), "to": stamp(s.end), "fps": s.fps,
                      "estimated_frames": frames, "estimated_sheets": math.ceil(frames / settings["frames_per_sheet"])})
    return {"passes": items, "estimated_frames": sum(i["estimated_frames"] for i in items),
            "estimated_sheets": sum(i["estimated_sheets"] for i in items)}


def prepare_output(video: Path, requested: Path | None, resume: bool) -> Path:
    default = video.with_name(f"{video.stem}_video_map")
    if resume:
        dest = (requested or default).expanduser().resolve()
        if not (dest / "manifest.json").is_file():
            raise ValueError(f"не найден существующий manifest.json: {dest}")
        return dest
    if requested:
        dest = requested.expanduser().resolve()
        if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
            raise FileExistsError(f"папка {dest} уже не пуста; используйте --resume или другую --output")
    else:
        dest = default
        suffix = 2
        while dest.exists():
            dest = default.with_name(f"{default.name}_{suffix}")
            suffix += 1
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def verify_resume(manifest: dict, video: Path, specs: list[PassSpec], settings: dict) -> list[PassSpec]:
    source = manifest["source"]
    if Path(source["path"]).resolve() != video or (
        source.get("signature") is not None and source["signature"] != signature(video)
    ) or (source.get("signature") is None and source.get("file_size") != video.stat().st_size):
        raise ValueError("исходное видео отличается от сохранённого проекта")
    if manifest["settings"] != settings:
        raise ValueError("параметры оформления отличаются от предыдущего запуска")
    saved = manifest["passes"]
    if saved[:len(specs)] != [x.to_dict() for x in specs]:
        raise ValueError("базовые проходы отличаются от предыдущего запуска; используйте те же параметры")
    # Additional passes inserted with `extend` are also resumed if interrupted.
    all_specs = [PassSpec(x["name"], x["start"], x["end"], x["fps"], x["kind"]) for x in saved]
    if source.get("signature") is None:
        source["signature"] = signature(video)
        manifest["schema_version"] = 2
    return all_specs


def add_range(project: Path, ffmpeg: Path, ffprobe: Path, start: float, end: float,
              fps: float, timeout: float, log) -> dict:
    manifest = load_project(project)
    video = video_path(manifest, project)
    info = probe(ffprobe, video)
    if end <= start or start >= info.duration or end > info.duration + 0.001:
        raise ValueError("временной диапазон выходит за пределы видео")
    end = min(end, info.duration)
    key = (round(start, 6), round(end, 6), round(fps, 6))
    for item in manifest["passes"]:
        if (round(item["start"], 6), round(item["end"], 6), round(item["fps"], 6)) == key:
            result = next((r for r in manifest.get("results", []) if r["name"] == item["name"]), None)
            if result and verify_pass(project, item["name"], manifest["settings"], result):
                log("диапазон уже создан, повторная обработка не требуется")
                return {**summary(project, manifest), "cached": True, "pass": item["name"]}
            # Identical request after an interrupted run: retry unfinished pass.
            spec = PassSpec(item["name"], item["start"], item["end"], item["fps"], item["kind"])
            if (project / spec.name).is_dir():
                raise RuntimeError("диапазон уже создан, но файлы повреждены; требуется ручная проверка")
            all_specs = [PassSpec(p["name"], p["start"], p["end"], p["fps"], p["kind"])
                         for p in manifest["passes"]]
            done = execute(project, video, ffmpeg, manifest, all_specs, timeout, log)
            return {**done, "cached": False, "pass": spec.name}
    index = 1
    existing = {p["name"] for p in manifest["passes"]}
    while True:
        name = f"extra_{index:02d}_{slug_time(start)}__{slug_time(end)}_{rate_label(fps)}"
        if name not in existing:
            break
        index += 1
    spec = PassSpec(name, start, end, fps, "extra")
    check_fps(spec, info)
    manifest["passes"].append(spec.to_dict())
    manifest["status"] = "incomplete"
    manifest["schema_version"] = 2
    manifest["source"]["signature"] = signature(video)
    save_manifest(project, manifest)
    # Finish any interrupted passes first, so `status=complete` is truthful.
    all_specs = [PassSpec(p["name"], p["start"], p["end"], p["fps"], p["kind"])
                 for p in manifest["passes"]]
    result = execute(project, video, ffmpeg, manifest, all_specs, timeout, log)
    return {**result, "cached": False, "pass": spec.name}


def locate(project: Path, start: float, end: float, limit: int) -> dict:
    manifest = load_project(project)
    if end <= start:
        raise ValueError("--end должен быть позже --start")
    if end > float(manifest["source"]["duration"]) + 0.001:
        raise ValueError("конец диапазона находится за пределами ролика")
    matches = []
    sheets = {}
    for item in manifest.get("results", []):
        folder = project_path(project, item["directory"])
        csv_path = folder / "frames.csv"
        if not csv_path.is_file():
            continue
        with csv_path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                try:
                    seconds = float(row["seconds"])
                except (ValueError, KeyError):
                    continue
                if start <= seconds < end:
                    sheet_path = str(folder / "sheets" / row["sheet"])
                    cell = int(row["cell"])
                    matches.append({"pass": item["name"], "time": row["timestamp"],
                                    "seconds": seconds, "sheet": sheet_path,
                                    "cell": cell, "row": int(row["row"]), "column": int(row["column"])})
                    key = (item["name"], sheet_path)
                    if key not in sheets:
                        sheets[key] = {"pass": item["name"], "sheet": sheet_path,
                                       "first_time": row["timestamp"], "last_time": row["timestamp"],
                                       "first_cell": cell, "last_cell": cell, "matched_frames": 0}
                    sheets[key]["matched_frames"] += 1
                    sheets[key]["last_time"] = row["timestamp"]
                    sheets[key]["last_cell"] = cell
    matches.sort(key=lambda item: (item["seconds"], item["pass"]))
    return {"project": str(project), "start": stamp(start), "end": stamp(end),
            "total": len(matches), "returned": min(len(matches), limit), "truncated": len(matches) > limit,
            "sheets": list(sheets.values()), "matches": matches[:limit]}


def extract_one(project: Path, ffmpeg: Path, at: float, output: Path | None,
                timeout: float, force: bool) -> dict:
    manifest = load_project(project)
    video = video_path(manifest, project)
    if at >= float(manifest["source"]["duration"]):
        raise ValueError("время должно быть меньше длительности ролика")
    dest = (output or (project / "original_frames" / f"frame_{slug_time(at)}.png")).expanduser().resolve()
    if dest.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("для кадра используйте расширение .png, .jpg или .webp")
    if dest == video:
        raise ValueError("нельзя перезаписать исходный файл")
    if dest.exists() and not force:
        if dest.is_file() and dest.stat().st_size > 0:
            return {"ok": True, "cached": True, "frame": str(dest), "at": stamp(at)}
        raise FileExistsError(f"файл уже существует: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    exact_frame(ffmpeg, video, at, dest, timeout)
    return {"ok": True, "cached": False, "frame": str(dest), "at": stamp(at),
            "source_resolution": f"{manifest['source']['width']}x{manifest['source']['height']}"}
