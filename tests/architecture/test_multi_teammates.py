from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from engine import AgentEngine
from llm import ModelClient, ModelError
from module3_host.api.app import create_app


@pytest.fixture
def game(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    engine = AgentEngine(ModelClient())
    path = tmp_path / "multi.sqlite3"
    with TestClient(create_app(path, engine)) as client:
        state = client.get("/api/state").json()
        client.headers["X-CSRF-Token"] = state["csrf"]
        registered = client.post("/api/users/register", json={
            "email": "multi@example.com", "password": "multi-password", "display_name": "联调玩家"
        }).json()
        client.headers["X-CSRF-Token"] = registered["csrf"]
        yield client, engine, path


def test_default_two_teammates_take_distinct_turns_and_share_public_evidence(game):
    client, _, _ = game
    state = client.post("/api/new", json={}).json()
    assert [m["name"] for m in state["teammates"]] == ["小夏", "阿澄"]
    state = client.post("/api/question", json={"text": "这与年龄有关吗？"}).json()
    assert state["next_teammate"]["name"] == "小夏"
    first = client.post("/api/teammate", json={}).json()
    assert first["next_actor"] == "teammate"
    assert first["next_teammate"]["name"] == "阿澄"
    assert client.post("/api/final", json={"text": "抢先提交"}).status_code == 409
    assert client.get("/api/state").json() == first
    final = client.post("/api/teammate", json={}).json()
    assert final["next_actor"] == "player"
    assert final["next_teammate"] is None
    turns = final["history"]
    assert [t.get("teammate_name") for t in turns] == [None, "小夏", "阿澄"]
    assert turns[1]["question"] != turns[2]["question"]
    repo = client.app.state.repository
    memory = repo.memory(final["game_id"])
    assert memory[1]["teammate_id"] != memory[2]["teammate_id"]
    assert memory[1]["target"] and memory[1]["rationale"]
    assert all(set(t) <= {"actor", "kind", "question", "verdict", "teammate_id", "teammate_name",
                          "target", "rationale"} for t in memory)


def test_second_teammate_failure_and_restart_reuse_question_and_identity(game, monkeypatch):
    client, engine, path = game
    client.post("/api/new", json={"teammate_count": 3})
    client.post("/api/question", json={"text": "录音有关吗？"})
    client.post("/api/teammate", json={})
    calls = []
    original_question = engine.question

    def propose(surface, memory, teammate, board=None):
        calls.append(deepcopy(teammate))
        assert memory[-1]["teammate_name"] == "小夏"
        return "这与时间有关吗？"

    def fail(*args):
        raise ModelError("模拟第二位队友判题失败")

    monkeypatch.setattr(engine, "teammate", propose)
    monkeypatch.setattr(engine, "question", fail)
    assert client.post("/api/teammate", json={}).status_code == 502
    state = client.get("/api/state").json()
    assert state["pending_question"] == "这与时间有关吗？"
    assert state["next_teammate"]["name"] == "阿澄"
    assert len(state["history"]) == 2
    monkeypatch.setattr(engine, "question", original_question)
    with TestClient(create_app(path, engine)) as restarted:
        restarted.cookies.update(dict(client.cookies))
        restarted.headers["X-CSRF-Token"] = state["csrf"]
        assert restarted.get("/api/state").json() == state
        retried = restarted.post("/api/teammate", json={}).json()
        assert retried["history"][-1]["teammate_name"] == "阿澄"
        assert retried["next_teammate"]["name"] == "小墨"
        assert len(calls) == 1


@pytest.mark.parametrize("count", [0, 4, True, "2", -1])
def test_teammate_count_validation(game, count):
    client, _, _ = game
    assert client.post("/api/new", json={"teammate_count": count}).status_code == 422


def test_three_teammates_and_demo_exhaustion_return_control(game):
    client, _, _ = game
    state = client.post("/api/new", json={"teammate_count": 3}).json()
    assert len(state["teammates"]) == 3
    for _ in range(3):
        client.post("/api/question", json={"text": "与年龄有关吗？"})
        for _ in range(3):
            state = client.post("/api/teammate", json={}).json()
            if state["next_actor"] == "player":
                break
        assert state["next_actor"] == "player"
    assert state["notice"]
    client.post("/api/new", json={"play_mode": "solo", "teammate_count": 3})
    assert client.get("/api/state").json()["teammates"] == []


def test_legacy_games_without_roster_keep_single_teammate_order(game):
    client, _, _ = game
    state = client.post("/api/new", json={}).json()
    repo = client.app.state.repository
    session, _ = repo.session(client.cookies.get("soup_session"))
    saved = repo.load_game(session["id"])
    saved.pop("teammates")
    saved.pop("teammate_index")
    repo.save_game(session["id"], saved)
    restored = client.get("/api/state").json()
    assert len(restored["teammates"]) == 1
    assert restored["game_id"] == state["game_id"]
    client.post("/api/question", json={"text": "身高有关吗？"})
    assert client.post("/api/teammate", json={}).json()["next_actor"] == "player"
