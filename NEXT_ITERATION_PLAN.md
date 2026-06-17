# KiMP3 Next Iteration Plan

## Статус На Текущий Момент

Общий статус: основная итерация реализована.

Сделано:

- [x] build-plan-first flow: Discover/Read/Enrich/Plan/Validate/Preview/Execute/Verify;
- [x] `auto` source context resolver: external -> `copy`, inside library -> `move`;
- [x] torrent-safe external copy: source не меняется, теги пишутся в temp-copy;
- [x] `OperationPlan`, `PathPlan`, `TagChangePlan`;
- [x] strict `AudioTags` на Pydantic с `TrackNumber`, `DiscNumber`, `Artwork`, `Lyrics`;
- [x] `TagBackend`, `Mp3Id3Backend`, `FlacVorbisBackend`, `TagWritePolicy`;
- [x] managed ID3 write без `easy_tags.delete()`;
- [x] path planning вынесен в `planning.py`, добавлен `%ext`;
- [x] новый `OperationExecutor` без legacy global lists;
- [x] full verify: path + managed tags + genre symlink;
- [x] dry-run read-only preview через Rich;
- [x] conflict resolver с default `keep-best`;
- [x] conflict policies: `keep-best`, `fail`, `skip`, `suffix`, `replace` + `force_replace`;
- [x] genre symlink sync, stale symlink cleanup, broken symlink cleanup внутри genre directory;
- [x] empty directory cleanup после успешных операций/maintenance;
- [x] metadata merge при replace-existing: большая обложка, library rating, library lyrics;
- [x] duplicate track number warning + очистка номера у более слабого кандидата;
- [x] Rich reporting: summary, plan table, details, execution result;
- [x] MP3 integration tests на реальном fixture;
- [x] legacy `file_operations.py` удалён.

Осталось / отложено:

- [ ] FLAC integration fixture test: backend реализован, но реального `.flac` fixture пока нет;
- [ ] настоящий audio fingerprint/chromaprint/acoustid для точного определения одинакового аудио;
- [ ] отдельное правило target audio hash/fingerprint equality;
- [ ] более глубокий merge `comment`, если будет решено, какие comment поля KiMP3 owns;
- [ ] более строгая политика отсутствующих path tags: сейчас используются fallback-значения, а не warning/error для каждого missing tag;
- [ ] `cut_empty_tags` как отдельная явная path-planning политика пока не нормализован.

## Цель

Сделать KiMP3 безопасным инструментом для двух сценариев:

- пополнение библиотеки из внешней временной директории, включая torrent-раздачи, которые нельзя менять;
- обслуживание уже существующей библиотеки: проверка путей, тегов и жанровых ссылок без лишних изменений.

Программа должна для каждого аудиофайла определить:

- какими должны быть нормализованные теги;
- где файл должен лежать в обслуживаемой библиотеке;
- какие genre symlink должны существовать;
- нужно ли реально что-то менять.

Если изменений не требуется, файл не трогается.

## Ключевое Решение

Порядок операций нужно изменить в начале следующей итерации. Без этого conflict detection, torrent-safe behavior и режим "не трогать если не надо" будут ненадежными.

Новый flow:

1. [x] Discover: найти аудиофайлы.
2. [x] Read: прочитать текущие теги без изменений файлов.
3. [x] Enrich: построить целевую модель тегов с учетом локальных данных, Last.FM, правил жанров и артиста.
4. [x] Plan: рассчитать целевой путь, действия с тегами и symlink.
5. [x] Validate: проверить конфликты, права, коллизии путей, валидность тегов и backend.
6. [x] Preview: показать полный план пользователю или dry-run.
7. [x] Execute: применить только валидные операции в безопасном порядке.
8. [x] Verify: перечитать результат и проверить, что файл, теги и ссылки соответствуют плану.

## Политика Источников

### Внешняя Директория

Если переданная директория находится вне `collection.directory`, режим по умолчанию: `copy`.

Правила:

- [x] source-файл не меняется никогда;
- [x] теги пишутся только в копию внутри библиотеки;
- [x] move запрещен по умолчанию, даже если пользователь явно не указал режим;
- [x] для torrent-раздач это сохраняет hash и возможность продолжать seed.

### Внутри Библиотеки

Если переданная директория равна `collection.directory` или находится внутри нее, режим по умолчанию: `move`.

Правила:

- [x] файл можно переименовать/переместить внутри библиотеки;
- [x] теги можно обновить in-place, если target path совпадает с текущим;
- [x] если путь и теги уже совпадают с планом, файл не трогается;
- [x] genre symlink синхронизируются с текущим планом.

### Явный Режим

`scan.move_or_copy` должен поддерживать:

- [x] `auto`: поведение по умолчанию, описанное выше;
- [x] `copy`: всегда копировать в библиотеку и писать теги только в копию;
- [x] `move`: перемещать, но запрещать для внешнего source без явного force-флага;
- [x] `none`: не перемещать файл, но разрешить планирование/проверку тегов и ссылок отдельно.

[x] Добавлен `force_external_move: false`.

## Новый Порядок Execute

### Для `copy`

1. [x] Создать целевые директории.
2. [x] Скопировать source во временный файл рядом с target, например `.filename.tmp-kimp3`.
3. [x] Записать теги во временный файл.
4. [x] Перечитать временный файл и проверить теги.
5. [x] Атомарно переименовать временный файл в target path.
6. [x] Создать/обновить genre symlink.
7. [x] Source оставить без изменений.

### Для `move` Внутри Библиотеки

1. [x] Если нужно изменить теги, записать их в текущий файл и проверить.
2. [x] Если нужно изменить путь, переместить файл в target path.
3. [x] Если target path уже совпадает, не делать move.
4. [x] Синхронизировать genre symlink.
5. [x] Удалить пустые директории только после успешных операций.

### Для `none`

1. [x] Не менять файл и не создавать копию.
2. [x] Можно построить отчет о расхождении тегов/пути/symlink.
3. [x] Symlink создавать только если это явно разрешено отдельной настройкой.

## Conflict Detection

Валидация должна происходить до любых изменений.

Проверять:

- [x] два source-файла планируются в один target path;
- [x] target path уже существует и не является тем же файлом;
- [~] target path существует и отличается по размеру/hash: размер участвует в keep-best scoring, hash/fingerprint отложен;
- [~] target path существует и имеет другой planned tag fingerprint: managed tag diff есть, existing target fingerprint частично покрыт metadata merge/scoring;
- [x] невозможно создать директорию;
- [x] невозможно писать в target directory;
- [x] backend не поддерживает формат файла;
- [x] pattern содержит неизвестные `%variables`;
- [x] target extension не совпадает с source extension.

Политики конфликта:

- [x] `fail`: остановить обработку конфликтующих файлов;
- [x] `skip`: пропустить конфликтующие файлы;
- [x] `suffix`: добавить суффикс к имени;
- [x] `replace`: разрешить только с явным force-флагом.

Режим по умолчанию изменён по решению итерации: [x] `keep-best`.

## Модель Тегов

Текущий `AudioTags` слишком свободный. Нужна строгая доменная модель.

Предлагаемая структура:

```python
class TrackNumber(BaseModel):
    number: int | None = None
    total: int | None = None

class DiscNumber(BaseModel):
    number: int | None = None
    total: int | None = None

class Artwork(BaseModel):
    data: bytes
    mime: str = "image/jpeg"
    kind: Literal["front"] = "front"

class Lyrics(BaseModel):
    text: str
    language: str = "eng"
    description: str = ""

class AudioTags(BaseModel):
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    track: TrackNumber = Field(default_factory=TrackNumber)
    disc: DiscNumber = Field(default_factory=DiscNumber)
    year: int | None = None
    genres: list[str] = Field(default_factory=list)
    lastfm_tags: list[str] = Field(default_factory=list)
    comment: str = ""
    compilation: bool = False
    rating: int | None = None
    artwork: Artwork | None = None
    lyrics: Lyrics | None = None
```

Правила:

- [x] внутри приложения жанры и Last.FM tags хранятся списками, а не comma-separated string;
- [x] форматирование строк для ID3/Vorbis выполняется только backend-ом записи;
- [x] rating хранится числом или отдельным типом, не строкой `"Rating: ..."`;
- [x] compilation парсится явно, `bool("0")` запрещен;
- [x] year валидируется как разумный год;
- [x] пустые строки нормализуются.

## Managed Fields

Нужно явно разделить поля:

- [x] managed by KiMP3;
- [x] read-only / preserved;
- [x] unknown frames.

По умолчанию KiMP3 должен менять только managed fields и не удалять неизвестные ID3 frames.

Managed fields для MP3:

- `TIT2` title;
- `TPE1` artist;
- `TALB` album;
- `TPE2` album artist;
- `TRCK` track number;
- `TPOS` disc number;
- `TDRC`/`TYER` date/year depending on ID3 version policy;
- `TCON` genre;
- selected `COMM` or `TXXX` fields for KiMP3-specific data;
- `APIC` front cover if artwork management enabled;
- `USLT` lyrics if lyrics management enabled.

[x] Не делать `easy_tags.delete()`.

## Backend Design

Ввести интерфейс:

```python
class TagBackend(Protocol):
    supported_extensions: set[str]

    def read(self, path: Path) -> AudioTags: ...
    def write(self, path: Path, tags: AudioTags, policy: TagWritePolicy) -> None: ...
    def verify(self, path: Path, expected: AudioTags, policy: TagWritePolicy) -> list[str]: ...
```

Backend-ы:

- [x] `Mp3Id3Backend` для `.mp3`;
- [x] `FlacVorbisBackend` для `.flac`, можно сделать второй фазой;
- [x] unsupported extension должен давать validation error, а не пустые теги.

## Path Planning

Вынести построение путей из `AudioFile.calculate_new_paths_from_tags()` в чистый сервис.

```python
class PathPlan(BaseModel):
    source_path: Path
    target_path: Path
    genre_links: list[Path]
    operation: Literal["copy", "move", "none"]
```

Правила:

- [x] extension берется из source-файла через `%ext` или автоматическую подстановку;
- [x] pattern variables валидируются;
- [x] `sanitize_path_component()` применяется ко всем path components, включая genre;
- [ ] `cut_empty_tags` реализуется явно или удаляется из config;
- [~] `Unknown` используется только если это разрешено политикой: fallback есть, отдельной политики нет;
- [~] если tag отсутствует и pattern требует его, planner должен выдать warning или validation error: частично через fallback, отдельные warnings отложены.

## Symlink Logic

Genre symlink должны быть частью плана, а не побочным эффектом `copy_to()` / `move_to()`.

Правила:

- [x] target для symlink лучше делать относительным;
- [x] сломанные symlink удалять только в пределах genre directory;
- [x] неправильные genre symlink удалять после успешного copy/move/write;
- [x] при `copy` source не должен быть target для genre symlink, target всегда файл в библиотеке.

## Dry Run

`dry_run` не должен менять filesystem.

Запрещено в dry-run:

- [x] `mkdir`;
- [x] `rmdir`;
- [x] `copy`;
- [x] `move`;
- [x] `symlink`;
- [x] запись тегов.

Dry-run должен только:

- [x] построить план;
- [x] выполнить read-only проверки;
- [x] показать diff тегов, path и symlink.

## Тесты Следующей Итерации

Минимальный набор:

- [x] external source defaults to copy;
- [x] source inside library defaults to move;
- [x] external copy writes tags only to copied file;
- [x] source file hash unchanged for external source;
- [x] existing correct library file is not touched;
- [x] `.flac` does not go through MP3 backend;
- [x] `%ext` preserves source extension;
- [x] duplicate target paths are detected before execution;
- [x] dry-run creates no directories/files;
- [x] `AudioTags` normalizes track/disc/year/genre/rating;
- [x] managed ID3 write does not delete unknown frames.

## Рекомендуемый Порядок Работ

1. [x] Добавить `auto` режим операции и resolver source context: external vs inside library.
2. [x] Ввести `OperationPlan`, `PathPlan`, `TagChangePlan` без изменения текущего executor.
3. [x] Переписать processing flow на build-plan-first.
4. [x] Добавить conflict detection до выполнения операций.
5. [x] Переписать dry-run как read-only preview.
6. [x] Ввести строгую Pydantic-модель `AudioTags` и адаптер совместимости для текущего кода.
7. [x] Ввести `Mp3Id3Backend`, убрать `easy_tags.delete()`.
8. [x] Перенести path rendering в отдельный модуль и добавить `%ext`.
9. [x] Переписать file executor под copy/move/none с безопасным порядком.
10. [x] Добавить FLAC backend или запретить `.flac` валидацией до реализации.
