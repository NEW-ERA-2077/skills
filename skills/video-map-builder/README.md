# Video Map Builder — инструмент и навык для ИИ-агентов

В комплекте: **Video Map Builder 2.0.0** (готовая программа) и `SKILL.md` (инструкция для Claude Code и Codex). Инструмент не требует внесения изменений для работы с навыком.

## Содержимое

```text
Video_Map_Builder/
├── video_map_builder/
│   ├── video_map_builder.py
│   ├── videomap/
│   ├── requirements.txt
│   ├── tests/
│   └── README_RU.md
├── SKILL.md
└── README.md
```

## Ручное размещение

1. **До запуска агента** положите папку `video_map_builder` целиком в корень рабочего проекта: `<проект>/video_map_builder/`. Не переносите из неё один лишь `.py`: программе нужны соседние модули в `videomap/`.
2. Разместите `SKILL.md` **вручную** в нужном каталоге навыков:
   - Claude Code: `<проект>/.claude/skills/video-map-builder/SKILL.md`;
   - Codex: `<проект>/.agents/skills/video-map-builder/SKILL.md`.
   При использовании обоих агентов можно положить копию одного и того же файла в каждый каталог. Папка инструмента в проекте общая.
3. Подготовьте Python 3.10+, FFmpeg (включая FFprobe) и зависимости программы. Подробности — в `video_map_builder/README_RU.md`.

**Важно:** агент сам **не устанавливает, не копирует, не перемещает и не редактирует** инструмент. Он обращается к уже размещённой программе. Если папка не найдена, агент сообщает об этом и просит указать существующий путь. Можно заранее дать ему свой путь к папке или к `video_map_builder.py`.

## Проверка вручную

Команды ниже выполняются из корня проекта, где размещена папка `video_map_builder`.

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
