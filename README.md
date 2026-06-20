# KiMP3 - Music Library Manager

KiMP3 is a Python-based music library manager for building and maintaining a self-contained music collection. It reads audio tags, enriches metadata, plans target paths and genre symlinks, validates conflicts, previews the result, and then applies only safe operations.

The main design goal is to keep the library usable without a database or proprietary music manager: metadata lives inside audio files, and the filesystem layout mirrors that metadata.

## Features

- Safe build-plan-first processing: discover, read, enrich, plan, validate, preview, execute, verify.
- Torrent-safe imports: external sources default to copy, and source files are not modified.
- In-library maintenance: files already inside the collection default to move/rename in place.
- No-op detection: files with correct path and managed tags are not touched.
- Managed MP3 ID3 and FLAC Vorbis backends.
- Last.FM enrichment, cover download, lyrics fetching, tag normalization and genre filtering.
- Relative genre symlinks with cleanup of stale/broken links inside the managed genre directory.
- Conflict resolution with `keep-best`, `fail`, `skip`, `suffix`, and force-gated `replace` policies.
- Rich dry-run preview and execution summaries.
- Automatic repair for common Cyrillic tag mojibake (`cp1251`/UTF-8 decoding issues).

## Installation

```bash
git clone https://github.com/kimifish/kimp3.git
cd kimp3
pip install .
```

For development:

```bash
pip install -e ".[dev]"
pytest
```

## Configuration Files

KiMP3 searches config files in this order:

1. `$XDG_CONFIG_HOME/kimp3/config.yaml`
2. `/etc/kimp3/config.yaml`
3. `./config/config.yaml`
4. `./config/config.example.yaml` as a project fallback

Use a specific config file with:

```bash
kimp3 --config /path/to/config.yaml
```

The project examples are:

- `config/config.example.yaml`: operational settings, paths, API keys, scan mode and LLM endpoint.
- `config/tags.example.yaml`: tag filtering rules, genre taxonomy, aliases and tag bans.

For every loaded `config.yaml`, KiMP3 also loads a sibling `tags.yaml` if it exists. If it does not exist, KiMP3 falls back to `tags.example.yaml` in the same directory. A tags file may either contain top-level `tags:` or the raw tag settings directly.

API keys can be stored in `$XDG_CONFIG_HOME/kimp3/.env` and referenced as `.env` in config:

```env
LASTFM_API_KEY=your_lastfm_api_key
LASTFM_API_SECRET=your_lastfm_api_secret
LASTFM_USERNAME=your_lastfm_username
LASTFM_PASSWORD_HASH=your_lastfm_password_hash
GENIUS_TOKEN=your_genius_token
```

## Normal Usage

The usual workflow is:

1. Edit `config/config.example.yaml` or your own `config.yaml`.
2. Set `collection.directory` to the managed music library.
3. Set `scan.dir_list` to the directories to process.
4. Run dry-run first.
5. Run normally if the plan looks correct.

Preview:

```bash
kimp3 --dry
```

Execute:

```bash
kimp3
```

Process a single directory without editing config:

```bash
kimp3 --scan_dir /path/to/incoming-music
```

Use a custom config and dry-run:

```bash
kimp3 --config ~/my-kimp3.yaml --scan_dir ~/Downloads/album --dry
```

CLI arguments currently supported:

- `-c`, `--config`: config file path.
- `-s`, `--scan_dir`: override `scan.dir_list` with one directory.
- `-D`, `--dry`: enable dry-run preview.

Most behavior is intentionally controlled by config rather than many CLI flags.

## Operation Modes

Set `scan.operation` in config.

```yaml
scan:
  operation: auto
```

Available modes:

- `auto`: default. External scan dirs are copied into the collection; files already inside `collection.directory` are moved/renamed in place.
- `copy`: always copy into the collection. Tags are written only to the copied file.
- `move`: move/rename files. External move requires `force_external_move: true`.
- `none`: report only. No file copy/move and no tag writes. Genre symlink creation is disabled unless `create_symlinks_in_none: true`.

Recommended defaults:

```yaml
scan:
  operation: auto
  force_external_move: False
```

## Dry Run

Dry-run is read-only. It must not create directories, copy/move files, create symlinks, delete files, or write tags.

```bash
kimp3 --dry
```

Dry-run prints a Rich preview with:

- operation summary;
- source and target paths;
- tag diffs;
- planned genre symlinks;
- conflict decisions;
- warnings and errors.

## Conflict Policies

Set `scan.conflict_policy`:

```yaml
scan:
  conflict_policy: keep-best
```

Available policies:

- `keep-best`: default. Score candidates and keep the better file/library target.
- `fail`: mark conflicts as errors and do not process conflicting plans.
- `skip`: skip conflicting plans.
- `suffix`: add a numeric suffix to conflicting target paths.
- `replace`: replace existing target only if `force_replace: true`.

Force replace example:

```yaml
scan:
  conflict_policy: replace
  force_replace: True
```

`keep-best` scoring considers format, readable audio info, file size, planned tag completeness, and a library-file bonus. When replacing an existing target, KiMP3 preserves selected library metadata: larger artwork, existing rating, and existing lyrics.

## Path Patterns

Paths are planned relative to `collection.directory`.

```yaml
paths:
  patterns:
    album: '%album_artist/%year - %album_title/%?disc_num{%disc_num-}%track_num. %song_title.%ext'
    compilation: '_Сборники/%album_title/%?disc_num{%disc_num-}%track_num. %song_artist - %song_title.%ext'
    genre: '_Жанры/%genre/%year. %song_artist - %song_title.%ext'
```

Supported variables:

- `%song_title`
- `%song_artist`
- `%album_title`
- `%album_artist`
- `%track_num`
- `%num_of_tracks`
- `%disc_num`
- `%genre`
- `%year`
- `%ext`

Unknown pattern variables are validation errors. Path components are sanitized before use.

Optional fragments use `%?field{...}`. The text inside braces is rendered only when
`field` is present; otherwise the whole fragment is removed with its punctuation and
spaces. For `%?disc_num{...}`, the fragment is rendered only for multi-disc albums
where `total_discs > 1` and `disc_number` is set.

Example single-disc result:

```text
Artist/2024 - Album/01. Song.mp3
```

Example multi-disc result:

```text
Artist/2024 - Album/2-01. Song.mp3
```

## Cleanup

Empty directory cleanup is controlled by:

```yaml
scan:
  delete_empty_dirs: True
  junk_files:
    - '.DS_Store'
    - 'Thumbs.db'
    - 'desktop.ini'
    - 'ehthumbs.db'
    - 'AlbumArtSmall.jpg'
```

Junk files are exact filenames only. Cleanup is limited to the relevant scan/genre roots and respects dry-run.

Broken symlink cleanup is controlled by:

```yaml
collection:
  clean_symlinks: True
```

Only symlinks inside the managed genre directory are cleaned.

## Metadata And Backends

Supported audio formats:

- `.mp3`: ID3 via `Mp3Id3Backend`.
- `.flac`: Vorbis comments via `FlacVorbisBackend`.

KiMP3 writes only managed fields and preserves unknown frames/comments by default. Managed fields include title, artist, album, album artist, track/disc numbers, year, genres, selected comments, artwork, lyrics, rating, and KiMP3/Last.FM-related fields.

## Tag Processing

Tag enrichment combines deterministic rules, Last.FM evidence and optional LLM suggestions.

Last.FM provides weighted flat tag lists from track, album and artist levels. KiMP3 keeps the source and weight of each candidate, with track tags ranked above album tags and album tags ranked above artist tags.

The optional LLM service is expected to return JSON with separate `genres` and `tags` lists. LLM suggestions are treated as evidence, not as final truth. They are normalized and filtered through the same deterministic rules as Last.FM tags.

`config/tags.example.yaml` defines three genre-related vocabularies:

- `genres`: canonical folder/player genres. These may become `AudioTags.genres` and create genre symlinks.
- `extended_genres`: recognized microgenres and styles. These are useful for semantic search tags but do not directly create folders.
- `genre_parents`: maps extended genres to canonical folder genres, for example `coldwave: dark wave` or `post-punk revival: post-punk`.

Selected canonical genres are also kept as semantic tags. Extended genres remain in the auxiliary tag list, so embeddings/search can still use precise descriptors without creating many nearly empty genre folders.

Tag filtering supports:

- exact banned tags;
- regex banned tags;
- artist-specific tag bans via `banned_artists_from_tags`;
- exact aliases via `similar_tags`;
- regex aliases via `similar_tags_patterns`.

Artist-specific bans are case-insensitive. This allows rules such as:

```yaml
tags:
  banned_artists_from_tags:
    post-punk:
      - ППВК
      - Первый Полёт в Космос
```

Debug logging includes the raw Last.FM track/album/artist tag lists with weights before filtering.

## Common Scenarios

Import from a torrent/incoming directory without changing source files:

```yaml
collection:
  directory: '/home/kimifish/Music'
scan:
  dir_list:
    - '/home/kimifish/Downloads/album'
  operation: auto
```

Then:

```bash
kimp3 --dry
kimp3
```

Maintain the existing library:

```yaml
collection:
  directory: '/home/kimifish/Music'
scan:
  dir_list:
    - '/home/kimifish/Music'
  operation: auto
```

Report only, without writing anything:

```yaml
scan:
  operation: none
```

Then:

```bash
kimp3
```

Always copy into the library:

```yaml
scan:
  operation: copy
```

Move external files intentionally:

```yaml
scan:
  operation: move
  force_external_move: True
```

## API Keys

Metadata enrichment can use:

- [Last.FM](https://www.last.fm/api/account)
- [Genius](https://genius.com/api-clients)

Fetching can be disabled:

```yaml
tags:
  fetch_tags: False
  fetch_album_cover: False
  fetch_lyrics: False
```

## Development

Run tests:

```bash
pytest
```

Useful checks:

```bash
black src/ tests/
isort src/ tests/
mypy src/kimp3/
pylint src/kimp3/
```

## License

MIT License.
