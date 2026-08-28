"""Plugin-local entry point that avoids changing Claude's PYTHONPATH."""

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from agentvast.observer.hook_collector import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
