# Video Map Builder — инструмент и навык для ИИ-агентов

В комплекте: **Video Map Builder 2.0.0** (готовая программа) и `SKILL.md` (инструкция для Claude Code и Codex). Инструмент не требует внесения изменений для работы с навыком.

## Содержимое

```text
video-map-builder/
├── video_map_builder/
│   ├── video_map_builder.py
│   ├── videomap/
│   ├── requirements.txt
│   ├── tests/
│   └── README_RU.md
├── SKILL.md
└── README.md
```

## Размещение и подготовка

1. Можно разместить папку `video_map_builder` целиком в корне проекта либо рядом с установленным `SKILL.md`, в том числе при глобальной установке. Не переносите один лишь `.py`: программе нужны соседние модули в `videomap/`. Если папки нет ни в проекте, ни рядом со скиллом, агент скачает её из [этого репозитория](https://github.com/NEW-ERA-2077/skills/tree/main/skills/video-map-builder/video_map_builder) в корень проекта. Комплектный глобальный скилл используется без копирования в проект.
2. При ручной установке разместите `SKILL.md` в нужном каталоге навыков, например:
   - Claude Code: `<проект>/.claude/skills/video-map-builder/SKILL.md`;
   - Codex: `<проект>/.agents/skills/video-map-builder/SKILL.md`.
   При использовании обоих агентов можно положить копию одного и того же файла в каждый каталог. Папка инструмента в проекте общая.
3. Агент проверит Python **3.10.3+**, FFmpeg и FFprobe. Если их нет, сообщит, что установить, и даст официальные ссылки для Windows: [Python](https://www.python.org/downloads/windows/) и [FFmpeg](https://ffmpeg.org/download.html#build-windows). Если они доступны, агент проверит Pillow и при отсутствии установит его через pip выбранного Python с учётом `requirements.txt`.

Можно заранее дать агенту свой путь к папке или к `video_map_builder.py`; он имеет приоритет. Существующие файлы инструмента агент не перезаписывает и не редактирует. Python и FFmpeg пользователь устанавливает самостоятельно; подготовку Pillow выполняет агент. Точные правила выбора пути, скачивания и проверки зависимостей — в `SKILL.md`.

## Проверка вручную

Команды ниже выполняются из корня проекта, где размещена папка `video_map_builder`. Это примеры ручного запуска: используйте Python 3.10.3+ с установленным Pillow. При другом расположении инструмента подставьте его абсолютный путь; агент использует интерпретатор, проверенный при подготовке.

**Windows (PowerShell):**

```powershell
py -3 .\video_map_builder\video_map_builder.py --help
py -3 .\video_map_builder\video_map_builder.py plan "D:\Videos\reference.mp4" --json
```

**Linux / macOS:**

```bash
python3 ./video_map_builder/video_map_builder.py --help
python3 ./video_map_builder/video_map_builder.py plan "/home/user/videos/reference.mp4" --json
```

`plan` оценивает объём работы, не создавая карту. В примерах замените путь к видео на реальный.

## Примеры заданий агенту

- «Создай карту кадров для `D:\Videos\reference.mp4` с помощью навыка video-map-builder».
- «В готовой карте найди кадры с `12:52` до `14:22`, не извлекай новые без необходимости».
- «Добавь подробные кадры с `12:52` до `14:22` в уже существующую карту».
- «Получить полноразмерный исходный кадр на `12:54.500`».
- «Инструмент расположен в `D:\Tools\video_map_builder` — используй именно этот путь».

Полная пользовательская справка по командам — в `video_map_builder/README_RU.md`, точные правила для агента — в `SKILL.md`.
