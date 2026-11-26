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


PLAN = {"scene": "住宅", "mechanism": "定时开关", "requirements": ["解释设置动机"]}
GRAPH = {"nodes": [{"id": "n1", "kind": "物品", "text": "灯"}], "edges": []}
CANDIDATE = {"story_graph": GRAPH, "puzzle": PUZZLE}


def test_rejected_story_is_revised_and_independently_reviewed():
    revised = {"story_graph": GRAPH, "puzzle": {**PUZZLE, "bottom": "为了方便照明，住户设置了定时开关，到时间灯自动亮起。"}}
    model = ScriptedModel([PLAN, CANDIDATE, {"approved": False, "feedback": "解释定时设置的动机"}, revised, {"approved": True, "feedback": ""}])
    result = AgentEngine(model).generate("灯")
    meta = result["generation"]
    assert meta["attempts"] == 2
    assert meta["trace"] == ["retrieval", "planner", "author", "reviewer", "revision", "reviewer"]
    assert model.calls[3]["review"] == "解释定时设置的动机"
    assert model.calls[3]["previous"] == CANDIDATE
    assert model.calls[4]["candidate"] == revised
    assert meta["story_graph"] == revised["story_graph"]
    assert len(meta["reviews"]) == 2
    assert len(model.calls) == 5


def test_review_failure_is_bounded_and_does_not_return_a_story():
    model = ScriptedModel([PLAN] + [CANDIDATE, {"approved": False, "feedback": "因果不成立"}] * 3)
    with pytest.raises(ModelError, match="限定次数"):
        AgentEngine(model).generate("灯")
    assert len(model.calls) == 7


@pytest.mark.parametrize("review", [{"approved": "true", "feedback": ""}, {"approved": False, "feedback": ""}, {"approved": True, "feedback": 2}])
def test_bad_reviewer_protocol_is_rejected(review):
    with pytest.raises(ModelError, match="审核结果无效"):
        AgentEngine(ScriptedModel([PLAN, CANDIDATE, review])).generate("灯")


def test_malformed_candidate_is_blocked_before_reviewer_then_repaired():
    model = ScriptedModel([PLAN, {"puzzle": {}}, CANDIDATE, {"approved": True, "feedback": ""}])
    assert AgentEngine(model).generate("灯")["title"] == PUZZLE["title"]
    assert model.calls[2]["previous"] == {"puzzle": {}}
    assert "候选必须" in model.calls[2]["review"]
    assert model.calls[3]["candidate"] == CANDIDATE
    assert len(model.calls) == 4


def test_zero_revisions_and_distinct_agent_prompts():
    from module1_puzzles.prompts import AUTHOR_PROMPT, REVISER_PROMPT
    assert AUTHOR_PROMPT != REVISER_PROMPT
    model = ScriptedModel([PLAN, CANDIDATE, {"approved": False, "feedback": "不合格"}])
    with pytest.raises(ModelError):
        AgentEngine(model, max_revisions=0).generate("灯")
    assert len(model.calls) == 3


def test_rag_uses_only_approved_puzzles_and_refreshes_source():
    from module1_puzzles.retrieval import ApprovedPuzzleRetriever
    library = [{"id": "old", **PUZZLE}]
    retriever = ApprovedPuzzleRetriever(lambda: library)
    assert retriever.search("灯") == []
    library.append({"id": "approved", **PUZZLE, "generation": {"approved": True}})
    assert [p["id"] for p in retriever.search("灯")] == ["approved"]
    assert retriever.search("xyz123") == []
    model = ScriptedModel([PLAN, CANDIDATE, {"approved": True, "feedback": ""}])
    result = AgentEngine(model, retriever=retriever).generate("灯")
    assert result["generation"]["reference_ids"] == ["approved"]
    assert all(call["references"][0]["id"] == "approved" for call in model.calls)


def test_unassemblable_candidate_never_reaches_model_reviewer():
    model = ScriptedModel([PLAN, {}])
    with pytest.raises(ModelError, match="限定次数"):
        AgentEngine(model, max_revisions=0).generate("灯")
    assert len(model.calls) == 2


def test_default_api_wires_rag_persists_graph_and_hides_secrets(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from module3_host.api.app import create_app
    from module3_host.storage import Repository
    from module1_puzzles.retrieval import ApprovedPuzzleRetriever
    model = ScriptedModel([PLAN, CANDIDATE, {"approved": True, "feedback": ""},
                           PLAN, CANDIDATE, {"approved": True, "feedback": ""}])
    monkeypatch.setattr("module3_host.api.app.ModelClient", lambda: model)
    database = tmp_path / "rag.sqlite3"
    with TestClient(create_app(database)) as client:
        client.headers["X-CSRF-Token"] = client.get("/api/state").json()["csrf"]
        registered = client.post("/api/users/register", json={
            "email": "workflow@example.com", "password": "workflow-password", "display_name": "流程玩家"
        }).json()
        client.headers["X-CSRF-Token"] = registered["csrf"]
        first = client.post("/api/new", json={"source": "new", "theme": "灯"})
        assert first.status_code == 200
        assert set(first.json()["puzzle"]) == {"title", "surface", "fact_count"}
        saved = Repository(database).puzzles()
        generated = [p for p in saved if p.get("generation", {}).get("approved")]
        assert len(generated) == 1
        assert generated[0]["generation"]["story_graph"] == GRAPH
        second = client.post("/api/new", json={"source": "new", "theme": "灯"})
        assert second.status_code == 200
        assert model.calls[3]["references"][0]["id"] == generated[0]["id"]
    assert ApprovedPuzzleRetriever(Repository(database).puzzles).search("灯")
