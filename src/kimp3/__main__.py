"""
Command-line interface for KiMP3
"""

import sys
from kimp3 import main, __version__

def entry_point():
    """Entry point for the command line interface"""
    if "--version" in sys.argv:
        print(f"KiMP3 version {__version__}")
        sys.exit(0)
    sys.exit(main())

if __name__ == "__main__":
    entry_point()
