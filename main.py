"""Atalho: `python main.py` (sem precisar instalar o pacote)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from emporio_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
