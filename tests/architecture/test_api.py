from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from module3_host.api.app import create_app
from llm import ModelClient, ModelError
from module1_puzzles.puzzles import DEMO_PUZZLES
from engine import AgentEngine
from module3_host.storage import Conflict


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    return AgentEngine(ModelClient())


@pytest.fixture
def client(tmp_path, engine):
    with TestClient(create_app(tmp_path / "game.sqlite3", engine)) as client:
        state = client.get("/api/state").json()
        client.headers["X-CSRF-Token"] = state["csrf"]
        yield client


def start(client, mode="coop", teammate_count=1):
    response = client.post("/api/new", json={"play_mode": mode, "teammate_count": teammate_count})
    assert response.status_code == 200, response.text
    return response.json()


def test_game_hides_secrets_enforces_turns_and_scores(client):
    state = start(client)
    assert set(state["puzzle"]) == {"title", "surface", "fact_count"}
    assert "solution" not in state
    response = client.post("/api/question", json={"text": "身高有关吗？"})
    assert response.json()["next_actor"] == "teammate"
    assert client.post("/api/question", json={"text": "录音有关吗？"}).status_code == 409
    assert client.post("/api/final", json={"text": "答案"}).status_code == 409
    state = client.post("/api/teammate", json={}).json()
    assert [t["actor"] for t in state["history"]] == ["player", "teammate"]
    state = client.post("/api/final", json={"text": "完全无关的故事"}).json()
    assert state["status"] == "scored"
    assert state["report"]["score"] == 0
    assert "bottom" in state["solution"]
    assert client.post("/api/question", json={"text": "还能问吗？"}).status_code == 409


def test_persistence_including_user_and_csrf_survives_new_app(tmp_path, engine):
    path = tmp_path / "restart.sqlite3"
    with TestClient(create_app(path, engine)) as first:
        state = first.get("/api/state").json()
        first.headers["X-CSRF-Token"] = state["csrf"]
        first.patch("/api/users/me", json={"display_name": "玩家甲"})
        start(first)
        expected = first.post("/api/question", json={"text": "与按钮有关吗？"}).json()
        cookies = dict(first.cookies)
    with TestClient(create_app(path, engine)) as second:
        second.cookies.update(cookies)
        assert second.get("/api/state").json() == expected
        assert second.get("/api/users/me").json()["display_name"] == "玩家甲"
        second.headers["X-CSRF-Token"] = state["csrf"]
        assert second.post("/api/teammate", json={}).status_code == 200


def test_cookie_isolation_and_csrf(client):
    start(client)
    with TestClient(client.app) as other:
        state = other.get("/api/state").json()
        assert state["status"] == "idle"
        assert other.post("/api/new", json={}).status_code == 403
    client.headers["X-CSRF-Token"] = "invalid"
    assert client.post("/api/reveal", json={}).status_code == 403


@pytest.mark.parametrize("data", [{"text": " "}, {"text": 123}, {"text": "问" * 301}, {"text": "问题", "bottom": "泄密"}])
def test_invalid_input_is_rejected_without_mutation(client, data):
    state = start(client)
    assert client.post("/api/question", json=data).status_code == 422
    assert client.get("/api/state").json() == state


def test_judgment_failure_keeps_question_for_retry_and_public_memory(client, engine, monkeypatch):
    start(client)
    client.post("/api/question", json={"text": "与身高有关吗？"})
    calls = []

    def teammate(surface, memory, profile, board=None):
        calls.append((surface, memory))
        assert all(set(m) == {"actor", "kind", "question", "verdict"} for m in memory)
        return "是录音吗？"

    original = engine.question
    monkeypatch.setattr(engine, "teammate", teammate)
    monkeypatch.setattr(engine, "question", lambda *args: (_ for _ in ()).throw(ModelError("模拟失败")))
    assert client.post("/api/teammate", json={}).status_code == 502
    failed = client.get("/api/state").json()
    assert len(failed["history"]) == 1
    assert failed["pending_question"] == "是录音吗？"
    monkeypatch.setattr(engine, "question", original)
    assert client.post("/api/teammate", json={}).json()["next_actor"] == "player"
    assert len(calls) == 1


def test_solo_and_reveal(client):
    start(client, "solo")
    for _ in range(2):
        assert client.post("/api/question", json={"text": "录音有关吗？"}).json()["next_actor"] == "player"
    assert client.post("/api/teammate", json={}).status_code == 409
    assert client.post("/api/reveal", json={}).json()["status"] == "revealed"


def test_failed_generation_does_not_replace_existing_game(client, engine, monkeypatch):
    before = start(client)
    monkeypatch.setattr(engine, "demo", False)
    monkeypatch.setattr(engine, "generate", lambda *args: (_ for _ in ()).throw(ModelError("审核未通过")))
    assert client.post("/api/new", json={"source": "new", "theme": "校园"}).status_code == 502
    after = client.get("/api/state").json()
    assert after["game_id"] == before["game_id"]
    assert after["puzzle"] == before["puzzle"]


def test_sqlite_concurrent_writes_allow_one_winner(client):
    start(client)
    repo = client.app.state.repository
    session, _ = repo.session(client.cookies.get("soup_session"))
    snapshot = repo.load_game(session["id"])

    def save(_):
        try:
            repo.save_game(session["id"], deepcopy(snapshot))
            return True
        except Conflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, range(2))) == [False, True]


def test_all_demo_solutions_can_score_full_marks(client):
    repo = client.app.state.repository
    session, _ = repo.session(client.cookies.get("soup_session"))
    for _ in range(2):
        start(client, "solo")
        puzzle = repo.load_game(session["id"])["puzzle"]
        state = client.post("/api/final", json={"text": puzzle["bottom"]}).json()
        assert state["status"] == "won"
        assert state["report"]["score"] == 100


def test_successful_generation_is_saved_but_keeps_secrets_private(client, engine, monkeypatch):
    puzzle = deepcopy(DEMO_PUZZLES[0])
    puzzle["id"] = "generated-test"
    puzzle.pop("rules")
    puzzle.pop("fact_rules")
    monkeypatch.setattr(engine, "demo", False)
    monkeypatch.setattr(engine, "generate", lambda theme: puzzle)
    state = client.post("/api/new", json={"source": "new", "theme": "校园"}).json()
    assert state["source"] == "new"
    assert "bottom" not in state["puzzle"]
    saved = client.app.state.repository.puzzles()
    assert any(p["id"] == "generated-test" for p in saved)
    assert all(p["id"] != "generated-test" for p in client.app.state.repository.puzzles(demo=True))


@pytest.mark.parametrize("action", ["question", "final"])
def test_player_model_failure_is_atomic(client, engine, monkeypatch, action):
    before = start(client)

    def fail(*args):
        raise ModelError("模拟模型失败")

    monkeypatch.setattr(engine, "question" if action == "question" else "score", fail)
    assert client.post(f"/api/{action}", json={"text": "有效输入"}).status_code == 502
    assert client.get("/api/state").json() == before


def test_turn_limit_still_allows_final_or_reveal(client):
    start(client, "solo")
    repo = client.app.state.repository
    session, _ = repo.session(client.cookies.get("soup_session"))
    game = repo.load_game(session["id"])
    game["history"] = [dict(actor="player", kind="question", question="身高有关吗？", verdict="正确", feedback="")] * 200
    repo.save_game(session["id"], game)
    assert client.post("/api/question", json={"text": "还能问吗？"}).status_code == 409
    assert client.post("/api/reveal", json={}).status_code == 200
