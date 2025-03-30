import sys
from importlib.metadata import version
from kimp3.main import main

__version__ = version("kimp3")

def run():
    sys.exit(main())