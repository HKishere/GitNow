"""PyInstaller entry wrapper: a plain script cannot use package-relative imports."""
import sys

from gitnow.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
