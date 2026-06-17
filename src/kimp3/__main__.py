"""
Command-line interface for KiMP3
"""

from kimp3 import main, __version__

def entry_point() -> None:
    """Entry point for the command line interface"""
    import sys

    if "--version" in sys.argv:
        print(f"KiMP3 version {__version__}")
        sys.exit(0)
    sys.exit(main())


def cli_main() -> None:
    entry_point()

if __name__ == "__main__":
    entry_point()
