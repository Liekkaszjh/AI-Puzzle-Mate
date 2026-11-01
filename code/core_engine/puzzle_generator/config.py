"""显式读取.env与模型配置；导入模块时不读取文件、不访问网络。"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import MutableMapping, Mapping

from .contracts import PuzzleError


def load_env_file(path: str | Path, environ: MutableMapping[str, str] | None = None) -> None:
    """支持KEY=value、引号与注释；不执行内容、不展开变量，现有环境变量优先。"""
    target = os.environ if environ is None else environ
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        raise PuzzleError("CONFIG_ERROR", "无法读取.env文件，请检查路径和权限。") from None
    values = {}
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise PuzzleError("CONFIG_ERROR", f".env第{number}行格式错误，需要KEY=value。")
        if value.startswith(("'", '"')):
            end = value.find(value[0], 1)
            if end < 0 or (value[end + 1:].strip() and not value[end + 1:].strip().startswith("#")):
                raise PuzzleError("CONFIG_ERROR", f".env第{number}行引号格式错误。")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        values[key] = value
    for key, value in values.items():
        target.setdefault(key, value)


@dataclass(frozen=True)
class ModelSettings:
    endpoint: str
    model: str
    api_key: str = field(default="", repr=False)
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ModelSettings":
        env = os.environ if environ is None else environ
        endpoint = env.get("PUZZLE_MODEL_ENDPOINT", "").strip()
        model = env.get("PUZZLE_MODEL_NAME", "").strip()
        if not endpoint or not model:
            raise PuzzleError("CONFIG_ERROR", "请填写PUZZLE_MODEL_ENDPOINT和PUZZLE_MODEL_NAME。")
        raw_timeout = env.get("PUZZLE_MODEL_TIMEOUT_MS", "60000").strip()
        if not re.fullmatch(r"[0-9]+", raw_timeout) or not 1 <= int(raw_timeout) <= 3_600_000:
            raise PuzzleError("CONFIG_ERROR", "PUZZLE_MODEL_TIMEOUT_MS须为1至3600000的整数毫秒。")
        return cls(endpoint, model, env.get("PUZZLE_MODEL_API_KEY", "").strip(), int(raw_timeout) / 1000)
