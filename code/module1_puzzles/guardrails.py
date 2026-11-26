"""Agent 交接护栏：输入/输出结构、长度、图谱完整性及失败反馈。"""
from llm import ModelError, require_text
from .kg import StoryGraph
from .puzzles import validate_generated


class GuardrailError(ModelError):
    """数据未通过节点边界检查，不得继续进入正常下游。"""


def validate_theme(theme):
    if not isinstance(theme, str) or not 1 <= len(theme.strip()) <= 100:
        raise GuardrailError("出题主题必须为1到100字符的非空字符串")
    return theme.strip()


def validate_references(references):
    if not isinstance(references, list) or len(references) > 10:
        raise GuardrailError("检索参考必须是最多10条的数组")
    cleaned = []
    try:
        for item in references:
            if not isinstance(item, dict):
                raise GuardrailError("检索参考必须是题目对象")
            reference = {key: require_text(item, key, limit) for key, limit in (
                ("id", 120), ("title", 80), ("surface", 1000), ("bottom", 4000))}
            points = item.get("key_points")
            if not isinstance(points, list) or not 1 <= len(points) <= 10:
                raise GuardrailError("检索参考缺少有效关键事实")
            reference["key_points"] = [require_text({"point": p}, "point", 500) for p in points]
            tags = item.get("tags", [])
            if not isinstance(tags, list) or len(tags) > 10:
                raise GuardrailError("检索参考标签无效")
            reference["tags"] = [require_text({"tag": tag}, "tag", 100) for tag in tags]
            cleaned.append(reference)
    except ModelError as exc:
        raise GuardrailError("检索参考未通过护栏：" + str(exc)) from exc
    return cleaned


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {"scene", "mechanism", "requirements"}:
        raise GuardrailError("规划必须且只能包含 scene、mechanism、requirements")
    try:
        requirements = plan["requirements"]
        if not isinstance(requirements, list) or not 1 <= len(requirements) <= 10:
            raise GuardrailError("规划 requirements 必须为1到10条设计要求")
        return {"scene": require_text(plan, "scene", 200), "mechanism": require_text(plan, "mechanism", 500),
                "requirements": [require_text({"requirement": r}, "requirement", 200) for r in requirements]}
    except ModelError as exc:
        raise GuardrailError("规划未通过护栏：" + str(exc)) from exc


def validate_candidate(candidate):
    if not isinstance(candidate, dict) or set(candidate) != {"story_graph", "puzzle"}:
        raise GuardrailError("候选必须且只能包含 story_graph 和 puzzle")
    try:
        graph = StoryGraph(candidate["story_graph"]).to_dict()
        puzzle = validate_generated(candidate["puzzle"])
        return {"story_graph": graph, "puzzle": {key: puzzle[key] for key in (
            "title", "surface", "bottom", "key_points")}}
    except ModelError as exc:
        raise GuardrailError("候选未通过护栏：" + str(exc)) from exc


def validate_review(result):
    if (not isinstance(result, dict) or set(result) != {"approved", "feedback"}
            or type(result["approved"]) is not bool or not isinstance(result["feedback"], str)
            or len(result["feedback"]) > 2000
            or (not result["approved"] and not result["feedback"].strip())):
        raise GuardrailError("审核结果无效，题目未入库")
    return {"approved": result["approved"], "feedback": result["feedback"].strip()}
