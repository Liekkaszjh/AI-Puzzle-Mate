import pytest

from llm import ModelError
from engine import AgentEngine


PUZZLE = dict(title="关灯之后", surface="屋里没人，灯却亮了。", bottom="定时开关控制灯。", key_points=["屋里没有人", "装有定时开关", "时间到了自动亮灯"])


class ScriptedModel:
    demo = False

    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def complete_json(self, system, payload, max_tokens=1200):
        self.calls.append(payload)
        return next(self.results)


def test_rejected_story_is_revised_and_independently_reviewed():
    model = ScriptedModel([PUZZLE, {"approved": False, "feedback": "解释定时设置的动机"}, PUZZLE, {"approved": True, "feedback": ""}])
    result = AgentEngine(model).generate("灯")
    assert result["generation"] == {"attempts": 2, "trace": ["author", "reviewer", "revision", "reviewer"]}
    assert model.calls[2]["review"] == "解释定时设置的动机"
    assert len(model.calls) == 4


def test_review_failure_is_bounded_and_does_not_return_a_story():
    model = ScriptedModel([PUZZLE, {"approved": False, "feedback": "因果不成立"}] * 3)
    with pytest.raises(ModelError, match="限定次数"):
        AgentEngine(model).generate("灯")
    assert len(model.calls) == 6


@pytest.mark.parametrize("review", [{"approved": "true", "feedback": ""}, {"approved": False, "feedback": ""}, {"approved": True, "feedback": 2}])
def test_bad_reviewer_protocol_is_rejected(review):
    with pytest.raises(ModelError, match="审核结果无效"):
        AgentEngine(ScriptedModel([PUZZLE, review])).generate("灯")
