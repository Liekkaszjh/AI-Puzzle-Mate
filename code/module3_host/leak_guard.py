"""泄底防护：公开反馈不得包含汤底或关键事实的实质片段。

汤主的模型反馈默认全部丢弃，本模块作为第二道保险，既可用于测试，
也可在将来允许模型生成澄清语时复用。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Set

from .contracts import clamp_feedback


def _compact(text: str) -> str:
    """去掉空白和标点，降低通过换行、空格、引号绕过的风险。"""
    normalized = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[\s\W_]+", "", normalized, flags=re.UNICODE)


def _ngrams(text: str, size: int) -> Set[str]:
    compact = _compact(text)
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[index:index + size] for index in range(len(compact) - size + 1)}


def contains_spoiler(candidate: str, puzzle: dict, *, size: int = 6, threshold: float = 0.5) -> bool:
    """判断候选文本是否大段复述汤底/关键事实。

    短反馈（例如“请拆成一次只问一件事”）不会因为个别字重合被拦截；
    只有连续片段覆盖达到阈值时才视为泄底。
    """
    if not isinstance(candidate, str) or not candidate.strip():
        return False
    compact_candidate = _compact(candidate)
    if not compact_candidate:
        return False

    sources = [puzzle.get("bottom", "")] + list(puzzle.get("key_points") or [])
    source_grams: Set[str] = set()
    for source in sources:
        if isinstance(source, str):
            compact_source = _compact(source)
            if len(compact_source) >= 4 and compact_source in compact_candidate:
                return True
            source_grams |= _ngrams(source, size)

    candidate_grams = _ngrams(candidate, size)
    if not candidate_grams or not source_grams:
        return False
    overlap = len(candidate_grams & source_grams) / len(candidate_grams)
    return overlap >= threshold


def sanitize_feedback(candidate: str, puzzle: dict, fallback: str = "") -> str:
    """不安全或超长的反馈统一替换为安全兜底文案。"""
    safe = clamp_feedback(candidate, fallback)
    if not safe:
        return ""
    if contains_spoiler(safe, puzzle):
        return clamp_feedback(fallback)
    return safe


def first_spoiler_source(candidate: str, puzzle: dict) -> str:
    """测试和排查用：返回第一个被命中的私密字段名。"""
    if contains_spoiler(candidate, puzzle):
        if isinstance(puzzle.get("bottom"), str) and _compact(puzzle["bottom"]) in _compact(candidate):
            return "bottom"
        for index, point in enumerate(puzzle.get("key_points") or []):
            if isinstance(point, str) and _compact(point) in _compact(candidate):
                return "key_points[%d]" % index
        return "ngram"
    return ""
