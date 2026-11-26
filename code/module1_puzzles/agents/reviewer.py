"""审核 Agent：只接收通过结构护栏的候选，审查故事质量。"""
from contracts import JsonModel
from ..guardrails import validate_theme, validate_references, validate_plan, validate_candidate, validate_review
from ..prompts import REVIEW_PROMPT


class ReviewerAgent:
    def __init__(self, model: JsonModel):
        self.model = model

    def run(self, theme, plan, references, candidate):
        payload = {"theme": validate_theme(theme), "plan": validate_plan(plan),
                   "references": validate_references(references), "candidate": validate_candidate(candidate)}
        return validate_review(self.model.complete_json(REVIEW_PROMPT, payload, max_tokens=1600))
