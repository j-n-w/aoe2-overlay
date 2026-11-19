"""Entry script for PyInstaller (it needs a file, not `python -m aoe2overlay`)."""

import sys

from aoe2overlay.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
