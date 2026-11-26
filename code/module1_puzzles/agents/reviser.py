"""修改 Agent：允许接收被护栏拒绝的旧候选，输出完整新版。"""
from copy import deepcopy
from contracts import JsonModel
from ..guardrails import GuardrailError, validate_theme, validate_references, validate_plan, validate_review
from ..prompts import REVISER_PROMPT


class ReviserAgent:
    def __init__(self, model: JsonModel):
        self.model = model

    def run(self, theme, plan, references, previous, review):
        if not isinstance(previous, dict):
            raise GuardrailError("待修复候选必须是JSON对象")
        feedback = validate_review({"approved": False, "feedback": review})["feedback"]
        payload = {"theme": validate_theme(theme), "plan": validate_plan(plan),
                   "references": validate_references(references),
                   "previous": deepcopy(previous), "review": feedback}
        return self.model.complete_json(REVISER_PROMPT, payload, max_tokens=4000)
