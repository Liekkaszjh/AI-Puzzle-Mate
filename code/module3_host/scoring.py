"""交卷评分：逐条核对关键事实，总分由 Python 计算，模型不能直接指定分数。"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from llm import ModelError

from .contracts import (
    MAX_ANSWER_LENGTH,
    final_outcome,
    normalize_puzzle,
    normalize_text,
)
from .prompts import SCORING_PROMPT

_STATUS_CREDIT = {"matched": 1.0, "partial": 0.5, "missing": 0.0, "contradicted": 0.0}

# 仅用于内置演示题的关键词评分；真实评分由模型逐条核验。
_DEMO_NEGATIONS = (
    "并非", "不是", "不矮", "不用伞", "没用伞", "没有录音", "没有定时", "不走楼梯",
)


def score_reconstruction(client: Any, puzzle: dict, text: str) -> Dict[str, Any]:
    """逐事实评分；满命中 1 分、部分 0.5 分、未命中或矛盾 0 分，换算百分制。"""
    normalized = normalize_puzzle(puzzle)
    answer = normalize_text(text, MAX_ANSWER_LENGTH, "还原答案")
    points = normalized["key_points"]

    if getattr(client, "demo", False):
        facts = _demo_facts(normalized, answer)
    else:
        data = client.complete_json(
            SCORING_PROMPT,
            {"bottom": normalized["bottom"], "key_points": points, "text": answer},
            max_tokens=1800,
        )
        if not isinstance(data, dict) or set(data) != {"facts"}:
            raise ModelError("评分结果必须只包含 facts 字段")
        facts = data.get("facts")

    details = _validate_facts(facts, points)
    score = round(100 * sum(item["credit"] for item in details) / len(details), 1)
    return {
        "score": score,
        "max_score": 100,
        "outcome": final_outcome(score),
        "matched_count": sum(item["status"] == "matched" for item in details),
        "partial_count": sum(item["status"] == "partial" for item in details),
        "missing_count": sum(item["status"] == "missing" for item in details),
        "contradicted_count": sum(item["status"] == "contradicted" for item in details),
        "total_facts": len(details),
        "facts": details,
        "answer": answer,
    }


def _demo_facts(puzzle: Dict[str, Any], text: str) -> List[Dict[str, Any]]:
    rules = puzzle.get("fact_rules")
    points = puzzle["key_points"]
    if not isinstance(rules, list) or len(rules) != len(points):
        raise ModelError("演示题的评分规则缺失或与关键事实数量不一致")

    clauses = re.split(r"[。！？；，\n]", text)
    facts: List[Dict[str, Any]] = []
    for index, groups in enumerate(rules):
        valid_groups: List[List[str]] = []
        if isinstance(groups, list):
            for group in groups:
                if not isinstance(group, list):
                    continue
                cleaned = [word for word in group if isinstance(word, str) and word]
                if cleaned:
                    valid_groups.append(cleaned)
        related = [
            clause for clause in clauses
            if any(word in clause for group in valid_groups for word in group)
        ]
        evidence = "，".join(related)
        hits = sum(any(word in evidence for word in group) for group in valid_groups)
        negative = any(
            any(word in clause for word in _DEMO_NEGATIONS) for clause in related
        )
        if negative:
            status = "contradicted"
        elif valid_groups and hits == len(valid_groups):
            status = "matched"
        elif hits:
            status = "partial"
        else:
            status = "missing"
        facts.append({
            "index": index,
            "status": status,
            "reason": "演示关键词评估：" + (evidence[:150] if evidence else "答案中未找到该事实的表述"),
        })
    return facts


def _validate_facts(facts: Any, points: List[str]) -> List[Dict[str, Any]]:
    """严格校验模型输出：条数、顺序、字段、枚举值和说明长度都必须匹配。"""
    if not isinstance(facts, list) or len(facts) != len(points):
        raise ModelError("评分结果未覆盖全部关键事实，请重新提交")
    details: List[Dict[str, Any]] = []
    for index, fact in enumerate(facts):
        if not isinstance(fact, dict) or set(fact) != {"index", "status", "reason"}:
            raise ModelError("评分返回的事实项必须且只能包含 index、status、reason")
        if type(fact.get("index")) is not int or fact["index"] != index:
            raise ModelError("评分返回的事实序号无效，请重新提交")
        status = fact.get("status")
        reason = fact.get("reason")
        if not isinstance(status, str) or status not in _STATUS_CREDIT:
            raise ModelError("评分返回的事实状态无效，请重新提交")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise ModelError("评分返回的事实说明为空或过长，请重新提交")
        details.append({
            "fact": points[index],
            "status": status,
            "credit": _STATUS_CREDIT[status],
            "reason": reason.strip(),
        })
    return details
