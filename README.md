# KiMP3 - Music Library Manager

KiMP3 is a powerful Python-based music library manager that helps create and maintain a self-contained music library. Its primary goal is to establish a music collection that remains fully functional without relying on external databases or management software. All metadata is stored within the audio files themselves and can be reflected in the directory structure, making your music library completely portable and future-proof.

## Philosophy

KiMP3 follows these core principles:

- **Self-Contained Library**: Your music collection should work without external databases or specialized software
- **File-Based Metadata**: All track information is stored in the audio files' tags, not in separate databases
- **Filesystem as Interface**: Directory structure reflects metadata, making it easy to browse and manage files using any file manager
- **Future-Proof Organization**: By avoiding proprietary databases and formats, your library remains accessible regardless of which music player or operating system you use
- **One-Time Setup**: Once organized, the library maintains its structure and can be used with any music player that supports standard audio formats and tags

## Features

- **Metadata Management**
  - Fetch and correct track metadata from Last.FM
  - Download high-quality album covers
  - Fetch lyrics from Lyrics.ovh and Genius
  - Smart tag correction and normalization
  - Genre detection based on Last.FM tags
  - All metadata is embedded directly in audio files

- **Library Organization**
  - Recursive directory scanning
  - Flexible file naming patterns that reflect metadata
  - Support for moving or copying files
  - Handling of compilations and albums
  - Cleanup of empty directories and broken symlinks
  - Creates a logical, browsable directory structure

- **Smart Caching**
  - Caches Last.FM API responses
  - Local storage for album covers
  - Memory-efficient operation
  - Cache management utilities

## Installation

1. Ensure you have Python 3.10 or newer installed
2. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/kimp3.git
   cd kimp3
   ```
3. Install using pip:
   ```bash
   pip install .
   ```

## Configuration

Create a `.env` file in your project directory with your API keys:
```env
LASTFM_API_KEY=your_lastfm_api_key
LASTFM_API_SECRET=your_lastfm_api_secret
GENIUS_TOKEN=your_genius_token
```

Configure the application by editing `config.yaml`:
```yaml
tags:
  fetch_tags: True
  fetch_album_cover: True
  fetch_lyrics: True
  autocorrection: True
  the_the: 'remove'  # Options: 'leave', 'move', 'remove'

scan:
  move_or_copy: 'copy'  # Options: 'move', 'copy'
  valid_extensions: ['.mp3', '.m4a', '.flac']
  skip_dirs: ['@eaDir', '@tmp']
  delete_empty_dirs: False
```

## Usage

Basic usage:
```bash
kimp3 /path/to/music/directory
```

Common options:
```bash
kimp3 --config custom_config.yaml  # Use custom config
kimp3 --dry-run                    # Preview changes without executing
kimp3 --verbose                    # Enable detailed logging
```

## API Keys

You'll need to obtain API keys from:
- [Last.FM](http://www.last.fm/api/account)
- [Genius](https://genius.com/api-clients)

## Dependencies

Main dependencies:
- `pylast`: Last.FM API client
- `music-tag`: Audio file tag manipulation
- `mutagen`: Audio metadata handling
- `pillow`: Image processing
- `rich`: Terminal formatting
- `beautifulsoup4`: Web scraping
- `requests`: HTTP client

## Cache Management

The application maintains several caches to improve performance:
- Artist and album name corrections
- Album track listings
- Genre information
- Artist and album tags
- Album covers (both in memory and on disk)

Clear caches using:
```python
from kimp3.tags import clear_cache
clear_cache()
```

## File Organization

Files are organized based on configurable patterns:
```yaml
paths:
  pattern: "{artist}/{album}/{track:02d} {title}"
  compilation_pattern: "Compilations/{album}/{track:02d} {artist} - {title}"
```

## Error Handling

The application handles various edge cases:
- Invalid or missing metadata
- Network connectivity issues
- File system permissions
- Unicode filename issues
- Duplicate files

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

Please ensure your code:
- Includes appropriate tests
- Follows PEP 8 style guidelines
- Includes documentation
- Maintains backward compatibility

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Last.FM for providing metadata API
- Genius for lyrics API
- Lyrics.ovh for additional lyrics source
- All contributors and users of the project

## Support

For issues and feature requests, please use the GitHub issue tracker.
