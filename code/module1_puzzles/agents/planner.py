"""规划 Agent：确定场景、机制和设计要求。"""
from contracts import JsonModel
from ..guardrails import validate_theme, validate_references, validate_plan
from ..prompts import PLANNER_PROMPT


class PlannerAgent:
    def __init__(self, model: JsonModel):
        self.model = model

    def run(self, theme, references):
        payload = {"theme": validate_theme(theme), "references": validate_references(references)}
        return validate_plan(self.model.complete_json(PLANNER_PROMPT, payload, max_tokens=1000))
