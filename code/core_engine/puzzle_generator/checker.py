"""先执行确定性的结构检查，再调用模型审核语义质量。"""

import re
import unicodedata
from copy import deepcopy

from .contracts import GenerationRequest, ModelGateway, PuzzleError, parse_model_object
from .prompts import REVIEW_CHECKS, review_messages
from .hint_rules import check_first_hint

TEXT_FIELDS = ("title", "theme", "difficulty", "surface", "solution")
LIST_FIELDS = ("key_facts", "clues", "hints")


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_text_list(value: object, *, allow_empty: bool = False) -> bool:
    return isinstance(value, list) and (allow_empty or bool(value)) and all(map(has_text, value))


def _normalize_item(text: str) -> str:
    # 保留加减号等有实际含义的符号。
    return re.sub(r"[\s，。！？、；：,.!?;:]", "", unicodedata.normalize("NFKC", text)).lower()


def check_structure(puzzle: object, request: GenerationRequest) -> list[str]:
    if not isinstance(puzzle, dict):
        return ["题目必须是一个对象。"]
    issues = []
    for field in TEXT_FIELDS:
        if not has_text(puzzle.get(field)):
            issues.append(f"{field}必须是非空字符串。")
    for field in LIST_FIELDS:
        values = puzzle.get(field)
        if not is_text_list(values):
            issues.append(f"{field}必须是非空字符串数组。")
        elif len(set(map(_normalize_item, values))) != len(values):
            issues.append(f"{field}存在重复内容，请合并或重写。")
    if not isinstance(puzzle.get("hints"), list) or len(puzzle["hints"]) != 3:
        issues.append("hints必须恰好包含三级提示。")
    elif has_text(puzzle.get("surface")) and is_text_list(puzzle["hints"]):
        issues.extend(check_first_hint(puzzle["surface"], puzzle["hints"][0]))
    if puzzle.get("theme") != request["theme"]:
        issues.append("题目主题与请求不一致。")
    if puzzle.get("difficulty") != request["difficulty"]:
        issues.append("题目难度与请求不一致。")
    return issues


def select_puzzle_fields(puzzle: dict) -> dict:
    return {field: deepcopy(puzzle[field]) for field in TEXT_FIELDS + LIST_FIELDS}


def _valid_causal_link(link: object, puzzle: dict) -> bool:
    if not isinstance(link, dict):
        return False
    indices = link.get("fact_indices")
    return (
        has_text(link.get("surface_event"))
        and link["surface_event"] in puzzle["surface"]
        and has_text(link.get("explanation"))
        and type(link.get("supported")) is bool
        and isinstance(indices, list)
        and (not link["supported"] or bool(indices))
        and all(type(index) is int and 0 <= index < len(puzzle["key_facts"]) for index in indices)
    )


def _validate_review(review: dict, puzzle: dict) -> None:
    checks, reasons, links = review.get("checks"), review.get("reasons"), review.get("causal_links")
    valid = (
        isinstance(checks, dict)
        and all(type(checks.get(key)) is bool for key in REVIEW_CHECKS)
        and isinstance(reasons, dict)
        and all(has_text(reasons.get(key)) for key in REVIEW_CHECKS)
        and is_text_list(review.get("issues"), allow_empty=True)
        and is_text_list(review.get("missing_premises"), allow_empty=True)
        and isinstance(links, list) and bool(links)
        and all(_valid_causal_link(link, puzzle) for link in links)
    )
    if not valid:
        raise PuzzleError("REVIEW_INVALID", "审核结果缺少必要检查项或存在无效引用。")


class PuzzleChecker:
    def __init__(self, model: ModelGateway) -> None:
        self.model = model

    def check(self, puzzle: object, request: GenerationRequest) -> dict:
        issues = check_structure(puzzle, request)
        if issues:
            return {"passed": False, "issues": issues, "checks": None}
        try:
            review = parse_model_object(self.model.complete(review_messages(puzzle, request)))
        except PuzzleError as error:
            if error.code == "MODEL_OUTPUT_INVALID":
                raise PuzzleError("REVIEW_INVALID", "审核结果格式错误，无法确认题目质量。") from None
            raise
        _validate_review(review, puzzle)
        checks = {key: review["checks"][key] for key in REVIEW_CHECKS}
        issues = list(review["issues"])
        unsupported = [link for link in review["causal_links"] if not link["supported"]]
        if unsupported or review["missing_premises"]:
            checks["consistency"] = checks["solvability"] = False
            issues.extend(f"未解释的异常：{link['surface_event']}；{link['explanation']}" for link in unsupported)
            issues.extend(f"缺少必要前提：{text}" for text in review["missing_premises"])
        failed = [key for key, passed in checks.items() if not passed]
        if failed and not issues:
            issues.append(f"以下检查未通过：{'、'.join(failed)}。")
        return {
            "passed": not failed and not issues,
            "issues": issues,
            "checks": checks,
            "reasons": {key: review["reasons"][key] for key in REVIEW_CHECKS},
            "causal_links": review["causal_links"],
            "missing_premises": review["missing_premises"],
        }
