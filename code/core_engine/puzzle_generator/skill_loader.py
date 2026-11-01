"""读取随Python包发布的出题Skill；每次构造提示词时读取最新内容。"""

from importlib.resources import files

from .contracts import PuzzleError


def load_puzzle_skill() -> str:
    resource = files("puzzle_generator").joinpath("skills", "puzzle-authoring", "SKILL.md")
    try:
        text = resource.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        raise PuzzleError("SKILL_LOAD_FAILED", "无法读取出题SKILL.md，请检查文件及安装包资源。") from None
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise PuzzleError("SKILL_INVALID", "出题SKILL.md缺少元信息头。")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise PuzzleError("SKILL_INVALID", "出题SKILL.md元信息头未闭合。") from None
    body = "\n".join(lines[end + 1:]).strip()
    if not body:
        raise PuzzleError("SKILL_INVALID", "出题SKILL.md正文不能为空。")
    return body
