"""组合Skill内容与模型输出协议；出题质量规则维护在SKILL.md。"""

import json

from .contracts import GenerationRequest, Message
from .skill_loader import load_puzzle_skill

REVIEW_CHECKS = (
    "consistency", "solvability", "no_spoilers",
    "hint_progression", "safety", "parameter_match",
)

GENERATION_PROTOCOL = '''以生成模式应用下列Skill。只输出JSON对象，不要Markdown。
结构：{"title":"标题","theme":"原主题","difficulty":"原难度","surface":"汤面","solution":"完整汤底","key_facts":["独立事实"],"clues":["关键线索"],"hints":["一级提示","二级提示","三级提示"]}。
所有字段必填。key_facts和clues为非空字符串数组，hints恰好三条。'''

REVIEW_PROTOCOL = '''以审核模式应用下列Skill。只输出JSON对象，包含：
checks：consistency、solvability、no_spoilers、hint_progression、safety、parameter_match六项布尔值。
reasons：与checks同名的六个字段，每项为简短的具体审核依据。
causal_links：非空数组，每项为
{"surface_event":"从汤面逐字摘录的连续片段","explanation":"已有解释或缺口说明","fact_indices":[0],"supported":true}。
fact_indices使用key_facts从0开始的下标；supported为false时允许空数组。
missing_premises：缺少的必要前提字符串数组。
issues：具体问题说明字符串数组，通过时为空。'''


def generation_messages(request: GenerationRequest, issues: list[str]) -> list[Message]:
    data = {
        **request,
        "previous_issues": issues,
        "instruction": "生成一份新的完整题目，并避免上一轮的问题。",
    }
    return [
        {"role": "system", "content": GENERATION_PROTOCOL + "\n\n" + load_puzzle_skill()},
        {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
    ]


def review_messages(puzzle: dict, request: GenerationRequest) -> list[Message]:
    return [
        {"role": "system", "content": REVIEW_PROTOCOL + "\n\n" + load_puzzle_skill()},
        {"role": "user", "content": json.dumps({"request": request, "puzzle": puzzle}, ensure_ascii=False)},
    ]
