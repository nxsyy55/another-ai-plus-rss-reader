"""Thin launcher. All CLI commands are defined in src/aiNewReader/cli.py."""
import sys
from pathlib import Path

# Ensure src/ is on the path when running as a script
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aiNewReader.cli import main

if __name__ == "__main__":
    main()
