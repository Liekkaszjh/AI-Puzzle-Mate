"""离线演示判题：只读取内置题的关键词规则，不调用模型。

演示规则是开发与课堂演示的降级路径，不承诺语义准确；正式判定需配置模型。
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from .contracts import VERDICT_IRRELEVANT, VERDICT_NO, VERDICT_YES, canonical_question_verdict

DEMO_FALLBACK = "演示模式只支持简单关键词判断；复杂问题建议接入模型。"
DEMO_NO_RULES = "这道演示题没有判题规则，请揭晓汤底或配置模型。"

# 只用于演示题的关键词否定翻转；不会用于真实模型判定。
_NEGATIONS = ("不是", "并非", "没有", "不需要", "不矮", "没带", "没用", "不用")


def judge_demo(puzzle: Dict[str, Any], text: str) -> Tuple[str, str]:
    """返回 (verdict, feedback)，verdict 为 是/不是/无关。"""
    rules = puzzle.get("rules")
    if not isinstance(rules, list) or not rules:
        return VERDICT_IRRELEVANT, DEMO_NO_RULES

    verdict = VERDICT_IRRELEVANT
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        keys = rule.get("keys")
        if not isinstance(keys, list) or not keys:
            continue
        if any(isinstance(key, str) and key and key in text for key in keys):
            verdict = canonical_question_verdict(rule.get("answer"))
            if verdict is None:
                verdict = VERDICT_IRRELEVANT
            break

    if verdict == VERDICT_IRRELEVANT:
        return verdict, DEMO_FALLBACK
    if any(word in text for word in _NEGATIONS):
        return (VERDICT_NO if verdict == VERDICT_YES else VERDICT_YES), ""
    return verdict, ""
