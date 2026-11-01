"""测试数据及顺序响应的模拟模型；不调用真实API。"""

import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "code" / "core_engine"))

REQUEST = {"theme": "校园", "difficulty": "普通"}
PUZZLE = {
    "title": "空白的画纸", **REQUEST,
    "surface": "画纸上没有颜料，老师却称赞小林完成了画作，这是为什么？",
    "solution": "这次是剪纸课，小林用剪下的轮廓完成了作品，所以不需要颜料。",
    "key_facts": ["这次是剪纸课", "画作由纸张的轮廓构成"],
    "clues": ["没有颜料不代表没有作品"],
    "hints": ["请留意汤面中的“画纸上没有颜料”。", "画纸本身也能变化", "想想剪刀能怎样改变纸张"],
}
APPROVED = {
    "checks": {
        "consistency": True, "solvability": True, "no_spoilers": True,
        "hint_progression": True, "safety": True, "parameter_match": True,
    },
    "reasons": {
        "consistency": "剪纸不需要颜料，解释了完成作品的原因。",
        "solvability": "没有颜料却完成画作提供了探索入口。",
        "no_spoilers": "汤面没有点明剪纸。",
        "hint_progression": "从没有颜料的异常到纸张变化，再到剪刀。",
        "safety": "日常课堂创作。", "parameter_match": "故事发生于校园。",
    },
    "causal_links": [{
        "surface_event": "画纸上没有颜料，老师却称赞小林完成了画作",
        "explanation": "剪纸依靠轮廓，不需要颜料。", "fact_indices": [0, 1], "supported": True,
    }],
    "missing_premises": [], "issues": [],
}


class ScriptedModel:
    def __init__(self, outputs):
        self.outputs = [item if isinstance(item, Exception) else deepcopy(item) for item in outputs]
        self.calls = []

    def complete(self, messages):
        self.calls.append(deepcopy(messages))
        if len(self.calls) > len(self.outputs):
            raise AssertionError("出现意外的模型调用")
        output = self.outputs[len(self.calls) - 1]
        if isinstance(output, Exception):
            raise output
        return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
