"""CLI for manual use and constrained machine-readable agent interactions."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import nonnegative_float, nonnegative_int, positive_float, positive_int, time_argument
from .media import probe, resolve_tool
from .project import (DEFAULTS, add_range, build_specs, create_manifest, estimate, execute,
                      extract_one, load_project, locate, prepare_output, save_manifest,
                      summary, verify_resume, video_path)


def base_parser(description: str) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=description,
                                   formatter_class=argparse.ArgumentDefaultsHelpFormatter)


def io_args(parser: argparse.ArgumentParser, *, include_ffprobe: bool = True) -> None:
    parser.add_argument("--ffmpeg", type=Path, help="путь к исполняемому файлу FFmpeg")
    if include_ffprobe:
        parser.add_argument("--ffprobe", type=Path, help="путь к исполняемому файлу FFprobe")
    parser.add_argument("--timeout", type=positive_float, default=3600.0,
                        help="предельное время одного запуска FFmpeg, секунд")
    parser.add_argument("--json", action="store_true", help="короткий JSON на stdout; сообщения о ходе работы на stderr")


def build_parser(*, planning: bool = False) -> argparse.ArgumentParser:
    parser = base_parser("Оценка объёма карты" if planning else "Карта видео: контакт-листы с точными таймкодами")
    parser.add_argument("video", nargs="?", type=Path, help="локальное видео")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--fps", type=positive_float, help="частота одного равномерного прохода")
    group.add_argument("--interval", type=positive_float, help="интервал одного равномерного прохода, секунд")
    parser.add_argument("--start", type=time_argument, default=0.0, help="начало одиночного прохода, ЧЧ:ММ:СС")
    end_group = parser.add_mutually_exclusive_group()
    end_group.add_argument("--end", type=time_argument, help="конец одиночного прохода, ЧЧ:ММ:СС")
    end_group.add_argument("--duration", type=positive_float, help="продолжительность одиночного прохода")
    parser.add_argument("--main-fps", type=positive_float, default=2.0)
    parser.add_argument("--overview-interval", type=positive_float, default=5.0)
    parser.add_argument("--hook-fps", type=positive_float, default=4.0)
    parser.add_argument("--hook-seconds", type=nonnegative_float, default=30.0)
    parser.add_argument("--no-overview", action="store_true")
    parser.add_argument("--no-hook", action="store_true")
    parser.add_argument("--detail", action="append", metavar="START-END@FPS", help="добавить подробный диапазон; повторяемый параметр")
    parser.add_argument("--frames-per-sheet", type=positive_int, default=25)
    parser.add_argument("--columns", type=positive_int, default=5)
    parser.add_argument("--thumb-width", type=positive_int, default=320)
    parser.add_argument("--gap", type=nonnegative_int, default=2)
    parser.add_argument("--timestamp-position", choices=["top-left", "top-right", "bottom-left", "bottom-right", "none"], default="top-left")
    parser.add_argument("--show-frame-number", action="store_true")
    parser.add_argument("--format", choices=["jpg", "png", "webp"], default="jpg")
    parser.add_argument("--quality", type=int, choices=range(50, 101), metavar="50..100", default=90)
    parser.add_argument("--keep-frames", action="store_true", help="оставлять отдельные сжатые кадры")
    if not planning:
        parser.add_argument("--output", type=Path, help="папка проекта; по умолчанию рядом с видео")
        parser.add_argument("--resume", "--reuse", dest="resume", action="store_true",
                            help="продолжить / использовать ранее готовые проходы без повторной обработки")
    io_args(parser)
    return parser


def other_parser(action: str) -> argparse.ArgumentParser:
    parser = base_parser({"extend": "Добавить подробный диапазон к существующей карте",
                          "locate": "Найти кадры и листы в интервале",
                          "frame": "Получить кадр из оригинала в полном разрешении",
                          "status": "Краткие сведения о проекте"}[action])
    parser.add_argument("--project", type=Path, required=True, help="папка готовой карты, содержащая manifest.json")
    if action in {"extend", "locate"}:
        parser.add_argument("--start", type=time_argument, required=True, help="начало диапазона")
        parser.add_argument("--end", type=time_argument, required=True, help="конец диапазона, не включая границу")
    if action == "extend":
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--fps", type=positive_float)
        group.add_argument("--interval", type=positive_float)
    if action == "locate":
        parser.add_argument("--limit", type=positive_int, default=50, help="сколько найденных кадров показывать в ответе")
    if action == "frame":
        parser.add_argument("--at", type=time_argument, required=True, help="время нужного кадра")
        parser.add_argument("--output", type=Path, help="путь к изображению, по умолчанию папка original_frames")
        parser.add_argument("--force", action="store_true", help="разрешить заменить существующее изображение")
    if action in {"extend", "frame"}:
        io_args(parser, include_ffprobe=action == "extend")
    else:
        parser.add_argument("--json", action="store_true", help="вывод в JSON")
    return parser


def show(data: dict, *, machine: bool) -> None:
    if machine:
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        return
    if data.get("estimated_frames") is not None:
        print(f"Примерно кадров: {data['estimated_frames']}; листов: {data['estimated_sheets']}")
        for item in data["passes"]:
            print(f"  {item['name']}: {item['from']}–{item['to']}, ~{item['estimated_frames']} кадров")
    elif data.get("matches") is not None:
        print(f"Найдено кадров: {data['total']}; листов: {len(data['sheets'])}; показано кадров: {data['returned']}")
        for sheet in data["sheets"]:
            print(f"  ЛИСТ [{sheet['pass']}] {sheet['sheet']} (ячейки {sheet['first_cell']}–{sheet['last_cell']})")
        for item in data["matches"]:
            print(f"  {item['time']}  [{item['pass']}] {item['sheet']}  ячейка {item['cell']} (строка {item['row']}, столбец {item['column']})")
        if data.get("truncated"):
            print("Результат сокращён; уменьшите диапазон или увеличьте --limit.")
    elif data.get("frame"):
        print(f"Кадр: {data['frame']}" + (" [из кэша]" if data.get("cached") else ""))
    else:
        print(f"Проект: {data['project']}")
        print(f"Состояние: {data['status']}; проходов: {data['passes']}; кадров: {data['frames']}; листов: {data['sheets']}")
        if data.get("cached"):
            print("Диапазон уже обработан — использованы существующие файлы.")


def settings_of(args) -> dict:
    return {field: getattr(args, field) for field in DEFAULTS}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    action = argv.pop(0) if argv and argv[0] in {"build", "plan", "extend", "locate", "frame", "status"} else "build"
    parser = build_parser(planning=action == "plan") if action in {"build", "plan"} else other_parser(action)
    args = parser.parse_args(argv)
    machine = args.json

    def log(message: str) -> None:
        print(message, file=sys.stderr if machine else sys.stdout)

    try:
        if action in {"build", "plan"}:
            if args.video is None:
                if machine or not sys.stdin.isatty():
                    parser.error("укажите путь к видео")
                value = input("Путь к видео: ").strip().strip('"')
                if not value:
                    parser.error("путь к видео не указан")
                args.video = Path(value)
            video = args.video.expanduser().resolve()
            if not video.is_file():
                raise FileNotFoundError(f"видео не найдено: {video}")
            if args.columns > args.frames_per_sheet:
                raise ValueError("--columns не может быть больше --frames-per-sheet")
            if args.thumb_width < 60:
                raise ValueError("ширина кадра должна быть не меньше 60 пикселей")
            ffprobe = resolve_tool("ffprobe", args.ffprobe)
            info = probe(ffprobe, video)
            specs = build_specs(args, info)
            settings = settings_of(args)
            if action == "plan":
                data = estimate(specs, settings)
            else:
                ffmpeg = resolve_tool("ffmpeg", args.ffmpeg)
                project = prepare_output(video, args.output, args.resume)
                if args.resume:
                    manifest = load_project(project)
                    specs = verify_resume(manifest, video, specs, settings)
                    log("Найдена существующая карта; готовые проходы будут пропущены.")
                else:
                    manifest = create_manifest(video, info, specs, settings, ffmpeg, ffprobe)
                    save_manifest(project, manifest)
                log(f"Видео: {video.name} ({info.duration:.2f} с). Результат: {project}")
                data = execute(project, video, ffmpeg, manifest, specs, args.timeout, log)
        elif action == "status":
            project = args.project.expanduser().resolve()
            data = summary(project, load_project(project))
        elif action == "locate":
            data = locate(args.project.expanduser().resolve(), args.start, args.end, args.limit)
        elif action == "extend":
            project = args.project.expanduser().resolve()
            ffmpeg = resolve_tool("ffmpeg", args.ffmpeg)
            ffprobe = resolve_tool("ffprobe", args.ffprobe)
            fps = args.fps if args.fps is not None else 1 / args.interval
            data = add_range(project, ffmpeg, ffprobe, args.start, args.end, fps, args.timeout, log)
        elif action == "frame":
            project = args.project.expanduser().resolve()
            ffmpeg = resolve_tool("ffmpeg", args.ffmpeg)
            data = extract_one(project, ffmpeg, args.at, args.output, args.timeout, args.force)
        else:
            raise AssertionError(action)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        if machine:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stdout)
        else:
            print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    show(data, machine=machine)
    return 0
