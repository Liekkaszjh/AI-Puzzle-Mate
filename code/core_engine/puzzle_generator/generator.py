"""生成候选题目，不负责审核和重试。"""

from .contracts import GenerationRequest, ModelGateway, parse_model_object
from .prompts import generation_messages
from .hint_rules import build_first_hint


class PuzzleGenerator:
    def __init__(self, model: ModelGateway) -> None:
        self.model = model

    def generate(self, request: GenerationRequest, issues: list[str] | None = None) -> dict:
        text = self.model.complete(generation_messages(request, issues or []))
        puzzle = parse_model_object(text)
        surface, hints = puzzle.get("surface"), puzzle.get("hints")
        if (isinstance(surface, str) and surface.strip() and isinstance(hints, list)
                and len(hints) == 3 and all(isinstance(hint, str) and hint.strip() for hint in hints)):
            # 一级只提供公开观察入口，二、三级保留模型输出并继续接受审核。
            puzzle["hints"] = [build_first_hint(surface), *hints[1:]]
        return puzzle
