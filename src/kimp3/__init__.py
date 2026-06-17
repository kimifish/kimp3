"""
KiMP3 - Self-contained music library manager
"""

__version__ = "1.0.0"


def main() -> int:
    from kimp3.main import main as run_main

    return run_main()

__all__ = ["main", "__version__"]
