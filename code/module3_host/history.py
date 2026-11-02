"""公开问答历史：归一化、摘要、重复问题定位。

汤主只能看到玩家已公开的问答记录；本文件不读取汤底，也不生成新内容。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .contracts import canonical_question_verdict

MAX_HISTORY_TURNS = 30
_MAX_QUESTION_CHARS = 300

# 让“他是否带伞”“他带伞了吗”归一到同一签名，“他是不是学生”和“他是学生吗”同理，
# 但保留“没/没有/不”等否定词，避免把肯定与否定混为一谈。
_PREFIX = re.compile(r"^(?:请问|想问一下|问一下|我想问|想问|那么|所以|那)")
_YES_NO_REPLACEMENTS = (
    ("是不是", "是"),
    ("有没有", "有"),
    ("会不会", "会"),
    ("能不能", "能"),
    ("可不可以", "可以"),
    ("对不对", "对"),
    ("行不行", "行"),
    ("好不好", "好"),
)
_TRAILING_PUNCTUATION = re.compile(r"[。！？!?；;，,、\s]+$")
_TRAILING_PARTICLE = re.compile(r"(?:吗|呢|吧|啊|呀|嘛|了)$")


def normalize_question(text: str) -> str:
    """生成用于重复检测的保守签名，不做同义词替换。"""
    value = unicodedata.normalize("NFKC", str(text)).strip().lower()
    value = re.sub(r"\s+", "", value)
    value = _PREFIX.sub("", value)
    for source, target in _YES_NO_REPLACEMENTS:
        value = value.replace(source, target)
    value = value.replace("是否", "")
    value = _TRAILING_PUNCTUATION.sub("", value)
    while True:
        stripped = _TRAILING_PARTICLE.sub("", value)
        if stripped == value:
            break
        value = stripped
    return value.strip()


def history_signature(text: str) -> str:
    return normalize_question(text)


def _question_turns(history: Optional[Iterable[Mapping[str, Any]]]) -> Iterable[Dict[str, Any]]:
    """只保留问句回合，兼容调用方未写 kind 的旧数据。"""
    for turn in history or []:
        if not isinstance(turn, Mapping):
            continue
        if turn.get("kind") not in (None, "question"):
            continue
        question = turn.get("question")
        verdict = canonical_question_verdict(turn.get("verdict"))
        if not isinstance(question, str) or not question.strip() or verdict is None:
            continue
        yield {"question": question.strip()[:_MAX_QUESTION_CHARS], "verdict": verdict}


def public_history(
    history: Optional[Iterable[Mapping[str, Any]]], limit: int = MAX_HISTORY_TURNS,
) -> List[Dict[str, str]]:
    """构造可传给模型的公开历史；默认只保留最近 30 条。"""
    turns = list(_question_turns(history))
    if limit > 0:
        turns = turns[-limit:]
    return turns


def find_prior(
    history: Optional[Iterable[Mapping[str, Any]]], question: str,
) -> Optional[Dict[str, str]]:
    """查找签名相同的既有问句，返回最近一次记录；没有则返回 None。"""
    signature = history_signature(question)
    if not signature:
        return None
    turns = list(_question_turns(history))
    for turn in reversed(turns):
        if history_signature(turn["question"]) == signature:
            return turn
    return None
