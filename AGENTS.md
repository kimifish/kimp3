# AGENTS.md - KiMP3 Development Guidelines

## Build/Lint/Test Commands

### Testing

- `pytest` - Run all tests
- `pytest tests/test_models.py::TestAudioTags::test_create_empty_tags` - Run single test
- `pytest -v` - Run tests with verbose output
- `pytest --cov=kimp3` - Run tests with coverage (if pytest-cov installed)

### Code Quality

- `isort src/ tests/` - Sort imports
- `mypy src/kimp3/` - Type checking
- `pylint src/kimp3/` - Code linting

### Development Setup

- `pip install -e ".[dev]"` - Install with development dependencies
- `python -m kimp3` - Run the application

## Code Style Guidelines

### Imports

- Use absolute imports: `from kimp3.models import AudioTags`
- Group imports: standard library, third-party, local modules
- Use `isort` for automatic import sorting
- Import classes from their actual modules: `from kimp3.song import AudioFile`

### Types

- Use type hints for all function parameters and return values
- Use `Optional[T]` for nullable types
- Use `Union[T, U]` for multiple possible types
- Use `List[T]`, `Dict[K, V]` instead of bare types

### Data Structures

- Use `@dataclass` for simple data containers
- Use `Enum` for constants and fixed sets of values
- Use `ABC` and `@abstractmethod` for interfaces

### Error Handling

- Use specific exception types, not bare `Exception`
- Log errors with appropriate levels using structured logging
- Use `try/except` blocks with specific exception handling

### Logging

- Use structured logger names: `log = logging.getLogger(f"{APP_NAME}.{__name__}")`
- Log at appropriate levels: DEBUG, INFO, WARNING, ERROR
- Include relevant context in log messages

### File Operations

- Use `pathlib.Path` for all path operations
- Handle file encoding explicitly when reading/writing text files
- Use context managers for file operations

### Testing

- Write descriptive test method names: `test_create_empty_tags`
- Use pytest fixtures for test setup
- Use `@pytest.mark.parametrize` for testing multiple inputs
- Mock external dependencies appropriately
- Fix import issues: import `AudioFile` from `kimp3.song`, not `kimp3.models`
- Use proper mutagen imports: `from mutagen._file import File` instead of `from mutagen import File`

### Documentation

- Use docstrings for all public functions/classes
- Follow Google-style docstrings with Args/Returns/Raises sections
- Keep docstrings concise but informative

### Naming Conventions

- Use `snake_case` for functions, variables, and methods
- Use `PascalCase` for classes and enums
- Use `UPPER_CASE` for constants
- Prefix private methods with single underscore: `_private_method`

### Console Output

- Use Rich library for formatted console output
- Prefer structured logging over print statements
- Use appropriate colors and formatting for user-facing messages

## Known Issues to Address

### Type Checking Errors

- Fix mutagen import: use `from mutagen._file import File` instead of `from mutagen import File`
- Fix AudioFile import in tests: import from `kimp3.song` instead of `kimp3.models`
- Fix AudioTags.from_mutagen method calls: provide both easy_tags and id3 parameters
- Fix None subscriptable error in models.py line 77

### Code Quality

- Run `mypy src/kimp3/` and fix type errors
- Run `pylint src/kimp3/` and address code quality issues
- Ensure all tests pass before committing changes
