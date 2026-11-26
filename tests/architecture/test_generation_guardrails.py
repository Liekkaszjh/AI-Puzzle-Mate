from copy import deepcopy

import pytest

from engine import AgentEngine
from llm import ModelError
from module1_puzzles.agents import PlannerAgent, AuthorAgent, ReviewerAgent, ReviserAgent
from module1_puzzles.guardrails import GuardrailError, validate_candidate, validate_review
from module1_puzzles.kg import GraphError, StoryGraph

from test_workflow import PLAN, GRAPH, PUZZLE, CANDIDATE, ScriptedModel


@pytest.mark.parametrize("plan", [None, {}, {**PLAN, "requirements": []},
                                  {**PLAN, "scene": 7}, {**PLAN, "extra": "忽略规则"}])
def test_bad_plan_is_blocked_before_author(plan):
    model = ScriptedModel([plan])
    with pytest.raises(GuardrailError):
        AgentEngine(model).generate("灯")
    assert len(model.calls) == 1


@pytest.mark.parametrize("theme", [None, "", " ", 42, "字" * 101])
def test_bad_theme_is_blocked_before_any_call(theme):
    model = ScriptedModel([])
    with pytest.raises(GuardrailError):
        AgentEngine(model).generate(theme)
    assert model.calls == []


@pytest.mark.parametrize("graph", [
    {}, {"nodes": [], "edges": []},
    {"nodes": GRAPH["nodes"] * 2, "edges": []},
    {"nodes": [{"id": "n1", "kind": [], "text": "灯"}], "edges": []},
    {"nodes": GRAPH["nodes"], "edges": [{"source": "n1", "relation": "因果", "target": "absent"}]},
    {"nodes": GRAPH["nodes"], "edges": [{"source": "n1", "relation": "未知关系", "target": "n1"}]},
    {"nodes": GRAPH["nodes"], "edges": [{"source": "n1", "relation": "因果", "target": "n1"}] * 2},
])
def test_malformed_graphs_are_rejected(graph):
    with pytest.raises(GraphError):
        StoryGraph(graph)


def test_graph_queries_are_cycle_safe_and_return_copies():
    data = {"nodes": [{"id": "a", "kind": "条件", "text": "定时到点"},
                      {"id": "b", "kind": "事件", "text": "灯亮起"},
                      {"id": "c", "kind": "人物", "text": "住户"}],
            "edges": [{"source": "a", "relation": "因果", "target": "b"},
                      {"source": "b", "relation": "因果", "target": "a"},
                      {"source": "c", "relation": "知情", "target": "a"}]}
    graph = StoryGraph(data)
    data["nodes"][0]["text"] = "外部修改"
    assert graph.node("a")["text"] == "定时到点"
    assert [node["id"] for node in graph.reachable("a", "因果")] == ["b"]
    assert graph.outgoing("a", "知情") == []
    snapshot = graph.to_dict()
    snapshot["nodes"].clear()
    assert len(graph.to_dict()["nodes"]) == 3
    with pytest.raises(KeyError):
        graph.node("absent")


@pytest.mark.parametrize("puzzle", [
    {**PUZZLE, "key_points": []}, {**PUZZLE, "key_points": ["重复", "重复。", "另一条"]},
    {**PUZZLE, "surface": "字" * 101}, {**PUZZLE, "bottom": ""},
])
def test_bad_puzzle_is_repaired_before_semantic_review(puzzle):
    bad = {"story_graph": GRAPH, "puzzle": puzzle}
    model = ScriptedModel([PLAN, bad, CANDIDATE, {"approved": True, "feedback": ""}])
    result = AgentEngine(model).generate("灯")
    assert result["generation"]["attempts"] == 2
    assert result["generation"]["reviews"][0]["approved"] is False
    assert model.calls[2]["previous"] == bad
    assert model.calls[3]["candidate"] == CANDIDATE


def test_invalid_revisions_cannot_bypass_guardrail_or_retry_limit():
    bad = {"story_graph": {"nodes": [], "edges": []}, "puzzle": PUZZLE}
    model = ScriptedModel([PLAN, bad, bad, bad])
    with pytest.raises(ModelError, match="限定次数"):
        AgentEngine(model).generate("灯")
    assert len(model.calls) == 4  # 规划一次、出题一次、修改两次；无模型审核。
    assert all("candidate" not in call for call in model.calls)


def test_bad_retrieval_is_blocked_before_planning():
    class BadRetriever:
        def search(self, theme):
            return [{"id": "incomplete"}]

    model = ScriptedModel([])
    with pytest.raises(GuardrailError):
        AgentEngine(model, retriever=BadRetriever()).generate("灯")
    assert model.calls == []


@pytest.mark.parametrize("review", [None, [], {"approved": 1, "feedback": ""},
                                    {"approved": False, "feedback": " "}])
def test_review_protocol_is_strict(review):
    with pytest.raises(GuardrailError):
        validate_review(review)


def test_agents_are_independently_callable_and_reviewer_blocks_invalid_input():
    model = ScriptedModel([PLAN, CANDIDATE, {"approved": False, "feedback": "补全设置动机"}, CANDIDATE])
    plan = PlannerAgent(model).run("灯", [])
    candidate = AuthorAgent(model).run("灯", plan, [])
    review = ReviewerAgent(model).run("灯", plan, [], candidate)
    assert ReviserAgent(model).run("灯", plan, [], candidate, review["feedback"]) == CANDIDATE
    assert len(model.calls) == 4
    with pytest.raises(GuardrailError):
        ReviewerAgent(model).run("灯", plan, [], {})
    assert len(model.calls) == 4


def test_candidate_validation_does_not_mutate_input():
    candidate = deepcopy(CANDIDATE)
    validated = validate_candidate(candidate)
    validated["story_graph"]["nodes"][0]["text"] = "changed"
    validated["puzzle"]["key_points"].clear()
    assert candidate == CANDIDATE
