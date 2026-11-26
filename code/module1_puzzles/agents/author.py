"""出题 Agent：返回候选图谱和题目，由交接护栏决定审核或修复。"""
from contracts import JsonModel
from ..guardrails import validate_theme, validate_references, validate_plan
from ..prompts import AUTHOR_PROMPT


class AuthorAgent:
    def __init__(self, model: JsonModel):
        self.model = model

    def run(self, theme, plan, references):
        payload = {"theme": validate_theme(theme), "plan": validate_plan(plan),
                   "references": validate_references(references)}
        return self.model.complete_json(AUTHOR_PROMPT, payload, max_tokens=4000)
