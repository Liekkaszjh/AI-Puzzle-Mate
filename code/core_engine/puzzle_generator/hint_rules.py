"""一级提示只引用公开汤面，防止引入汤底中的隐藏机制。"""

import re

FIRST_HINT_PREFIX = "请留意汤面中的“"
FIRST_HINT_SUFFIX = "”。"


def build_first_hint(surface: str) -> str:
    """选取公开异常句子，不调用模型、不引入汤底解释。"""
    sentences = [match.strip() for match in re.findall(r"[^。！？\n]+[。！？]?", surface) if match.strip()]
    if not surface.strip():
        raise ValueError("汤面不能为空。")
    if not sentences:
        sentences = [surface.strip()]
    focus = next((sentence for sentence in sentences
                  if any(word in sentence for word in ("却", "反而", "突然", "每次", "仍然", "但是"))), sentences[0])
    # 截取后仍是汤面的连续原文，不在引号内追加省略号或解释。
    return f"{FIRST_HINT_PREFIX}{focus[:80]}{FIRST_HINT_SUFFIX}"


def check_first_hint(surface: str, hint: str) -> list[str]:
    if hint.startswith(FIRST_HINT_PREFIX) and hint.endswith(FIRST_HINT_SUFFIX):
        excerpt = hint[len(FIRST_HINT_PREFIX):-len(FIRST_HINT_SUFFIX)]
        if excerpt.strip() and excerpt in surface:
            return []
    return ["一级提示只能引用汤面原文，格式为：请留意汤面中的“汤面连续原文片段”。不得解释隐藏机制。"]
