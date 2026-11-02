"""模块3的公共数据约定、判定词表和输入校验。

对外只暴露三种问句判定：是 / 不是 / 无关；还原判定：正确 / 部分正确 / 错误。
本文件不调用模型，也不依赖模块4，便于单独测试和替换调用方。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

MAX_QUESTION_LENGTH = 300
MAX_ANSWER_LENGTH = 1500
MAX_FEEDBACK_LENGTH = 120

VERDICT_YES = "是"
VERDICT_NO = "不是"
VERDICT_IRRELEVANT = "无关"
QUESTION_VERDICTS: Tuple[str, ...] = (VERDICT_YES, VERDICT_NO, VERDICT_IRRELEVANT)

FINAL_CORRECT = "正确"
FINAL_PARTIAL = "部分正确"
FINAL_WRONG = "错误"
FINAL_VERDICTS: Tuple[str, ...] = (FINAL_CORRECT, FINAL_PARTIAL, FINAL_WRONG)

# 兼容旧版 正确/错误 文案、模型常见英文输出和简单同义写法。
# 键统一使用小写；中文不受 lower() 影响。
_QUESTION_ALIASES = {
    "是": VERDICT_YES,
    "是的": VERDICT_YES,
    "对": VERDICT_YES,
    "对的": VERDICT_YES,
    "正确": VERDICT_YES,
    "有": VERDICT_YES,
    "yes": VERDICT_YES,
    "y": VERDICT_YES,
    "true": VERDICT_YES,
    "1": VERDICT_YES,
    "不是": VERDICT_NO,
    "否": VERDICT_NO,
    "不对": VERDICT_NO,
    "错误": VERDICT_NO,
    "没有": VERDICT_NO,
    "no": VERDICT_NO,
    "n": VERDICT_NO,
    "false": VERDICT_NO,
    "0": VERDICT_NO,
    "无关": VERDICT_IRRELEVANT,
    "不相关": VERDICT_IRRELEVANT,
    "无关紧要": VERDICT_IRRELEVANT,
    "irrelevant": VERDICT_IRRELEVANT,
    "unknown": VERDICT_IRRELEVANT,
    "n/a": VERDICT_IRRELEVANT,
    "na": VERDICT_IRRELEVANT,
}

_VERDICT_CODES = {
    VERDICT_YES: "yes",
    VERDICT_NO: "no",
    VERDICT_IRRELEVANT: "irrelevant",
    FINAL_CORRECT: "correct",
    FINAL_PARTIAL: "partial",
    FINAL_WRONG: "wrong",
}


@dataclass(frozen=True)
class HostAnswer:
    """汤主一次判定的完整结果；面向调用方，不直接序列化给浏览器。"""

    verdict: str
    feedback: str = ""
    # guard / history / demo / model / scoring
    source: str = "model"
    # yes / no / irrelevant / correct / partial / wrong
    canonical: str = ""
    history_size: int = 0
    report: Optional[Dict[str, Any]] = None
    timings_ms: Dict[str, int] = field(default_factory=dict)


def normalize_puzzle(puzzle: object) -> Dict[str, Any]:
    """校验并复制题目；不修改调用方字典，避免跨会话串改。"""
    if not isinstance(puzzle, Mapping):
        raise ValueError("题目必须是字典")
    bottom = puzzle.get("bottom")
    if not isinstance(bottom, str) or not bottom.strip():
        raise ValueError("题目缺少非空汤底 bottom")
    points = puzzle.get("key_points")
    if not isinstance(points, (list, tuple)) or not 1 <= len(points) <= 20:
        raise ValueError("题目必须包含 1 到 20 条关键事实")
    normalized_points = []
    for point in points:
        if not isinstance(point, str) or not point.strip() or len(point.strip()) > 200:
            raise ValueError("关键事实必须是非空字符串且不超过 200 字")
        normalized_points.append(point.strip())

    normalized = dict(puzzle)
    normalized["bottom"] = bottom.strip()
    normalized["key_points"] = normalized_points
    surface = puzzle.get("surface")
    if isinstance(surface, str):
        normalized["surface"] = surface.strip()
    return normalized


def normalize_text(value: object, limit: int, field_name: str) -> str:
    """去除首尾空白并限制长度；错误信息可直接展示。"""
    if not isinstance(value, str):
        raise ValueError("%s必须是文本" % field_name)
    text = value.strip()
    if not text:
        raise ValueError("%s不能为空" % field_name)
    if len(text) > limit:
        raise ValueError("%s不能超过 %d 字" % (field_name, limit))
    return text


def canonical_question_verdict(value: object) -> Optional[str]:
    """把模型或历史中的判定统一成 是/不是/无关；无法识别时返回 None。"""
    if not isinstance(value, str):
        return None
    return _QUESTION_ALIASES.get(value.strip().lower())


def verdict_code(verdict: str) -> str:
    """给前端/日志使用的稳定英文码。"""
    return _VERDICT_CODES.get(verdict, "")


def final_outcome(score: float) -> str:
    """按百分制得分给出三级还原结论。"""
    if score >= 100:
        return FINAL_CORRECT
    if score <= 0:
        return FINAL_WRONG
    return FINAL_PARTIAL


def clamp_feedback(feedback: str, fallback: str = "") -> str:
    """反馈只保留一行且不超过约定长度，避免调用方渲染超长文本。"""
    if not isinstance(feedback, str):
        return fallback
    text = " ".join(feedback.split())
    if not text:
        return fallback
    return text[:MAX_FEEDBACK_LENGTH]
