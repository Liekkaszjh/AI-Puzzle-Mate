"""无需安装包即可从仓库运行真实API测试；不会被unittest自动发现。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "code" / "core_engine"))

from puzzle_generator.cli import main  # noqa: E402


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main(
        default_env_file=PROJECT_ROOT / ".env",
        default_output_dir=PROJECT_ROOT / "tests" / "integration" / "output",
    ))
