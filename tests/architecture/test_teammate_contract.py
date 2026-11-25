import pytest
from fastapi.testclient import TestClient

from engine import AgentEngine
from llm import ModelError
from module1_puzzles.puzzles import DEMO_PUZZLES
from module2_teammate import (DEMO_CLUES, DUPLICATE_THRESHOLD, GENERIC_CLUES, TEAMMATES,
                              DuplicateQuestion, duplicate_of, propose_turn, similarity)
from module3_host.api.app import create_app


class DemoClient:
    demo = True


class ElevatorGame:
    """LLM 模式但判题固定为无关：只验证队友回合的协议与失败处理。"""

    demo = False

    def __init__(self, proposal):
        self.proposal = proposal
        self.calls = 0

    def complete_json(self, system, payload, max_tokens=1200):
        if "surface" in payload:
            self.calls += 1
            return self.proposal
        return {"verdict": "无关", "feedback": ""}


def start(client):
    registered = client.post("/api/users/register", json={
        "email": "teammate@example.com", "password": "teammate-password", "display_name": "协作玩家"
    })
    assert registered.status_code == 200
    client.headers["X-CSRF-Token"] = registered.json()["csrf"]
    response = client.post("/api/new", json={"source": "existing", "play_mode": "coop", "theme": ""})
    assert response.status_code == 200


def test_similarity_tells_paraphrase_from_new_proposition():
    # 同义改写：换主语、换虚词、加“有关系吗”仍算同一命题。
    assert similarity("这和身高有关吗？", "这与他的身高有关吗？") >= DUPLICATE_THRESHOLD
    assert similarity("这和身高有关吗？", "和身高有关系吗？") >= DUPLICATE_THRESHOLD
    assert similarity("邻居出差前忘记关闭定时播放了吗？", "邻居出差前忘了关定时播放吗？") >= DUPLICATE_THRESHOLD
    # 不同命题：维度不同、对象不同、正反不同，都不能被判成重复。
    assert similarity("这和身高有关吗？", "这和年龄有关吗？") < DUPLICATE_THRESHOLD
    assert similarity("这和身高有关吗？", "雨伞能帮他按按钮吗？") < DUPLICATE_THRESHOLD
    assert similarity("这和录音有关吗？", "这和录像有关吗？") < DUPLICATE_THRESHOLD
    assert duplicate_of("这与他的身高有关吗？", ["这和身高有关吗？"]) == "这和身高有关吗？"
    assert duplicate_of("这和年龄有关吗？", ["这和身高有关吗？"]) is None


def test_demo_turn_is_structured_and_rotates_by_teammate():
    surface = DEMO_PUZZLES[0]["surface"]
    first = propose_turn(DemoClient(), surface, [], TEAMMATES[0])
    assert set(first) == {"question", "target", "rationale"}
    assert first["question"] == DEMO_CLUES["elevator"][0]["question"]
    second = propose_turn(DemoClient(), surface, [], TEAMMATES[1])
    assert second["question"] == DEMO_CLUES["elevator"][1]["question"]
    # 同一队友在已有问答后跳过已问过的线索，不会原样重问。
    history = [{"actor": "teammate", "question": DEMO_CLUES["elevator"][0]["question"]}]
    third = propose_turn(DemoClient(), surface, history, TEAMMATES[0])
    assert third["question"] == DEMO_CLUES["elevator"][1]["question"]


def test_demo_clues_never_borrow_another_puzzle_answer():
    unrelated = "一辆自行车停在门口，第二天车铃自己响了，主人却一点也不奇怪。为什么？"
    turn = propose_turn(DemoClient(), unrelated, [], TEAMMATES[0])
    assert turn["question"] in {clue["question"] for clue in GENERIC_CLUES}
    assert turn["question"] not in {clue["question"] for clue in DEMO_CLUES["recording"]}


def test_duplicate_question_retries_once_then_yields_to_player(tmp_path):
    engine = AgentEngine(ElevatorGame({"question": "这与他的身高有关吗？", "target": "身高",
                                       "rationale": "先确认身高"}))
    with TestClient(create_app(tmp_path / "duplicate.sqlite3", engine)) as client:
        state = client.get("/api/state").json()
        client.headers["X-CSRF-Token"] = state["csrf"]
        start(client)
        client.post("/api/question", json={"text": "这和身高有关吗？"})
        assert client.post("/api/teammate", json={}).status_code == 200
        state = client.get("/api/state").json()
        assert engine.model.calls == 2  # 只重试一次，不无限重发
        assert "重复" in state["notice"]
        assert state["next_actor"] == "player"
        assert [turn["actor"] for turn in state["history"]] == ["player"]


def test_invalid_teammate_payload_is_not_written_to_history(tmp_path):
    engine = AgentEngine(ElevatorGame({"question": "只给了问题"}))
    with TestClient(create_app(tmp_path / "invalid.sqlite3", engine)) as client:
        state = client.get("/api/state").json()
        client.headers["X-CSRF-Token"] = state["csrf"]
        start(client)
        client.post("/api/question", json={"text": "这和身高有关吗？"})
        assert client.post("/api/teammate", json={}).status_code == 502
        assert [turn["actor"] for turn in client.get("/api/state").json()["history"]] == ["player"]


def test_legacy_string_result_is_still_accepted(tmp_path):
    engine = AgentEngine(ElevatorGame({"question": "这与时间有关吗？", "target": "时间",
                                       "rationale": "先确认时间"}))
    engine.teammate = lambda surface, memory, teammate=None, board=None: "这与时间有关吗？"
    with TestClient(create_app(tmp_path / "legacy.sqlite3", engine)) as client:
        state = client.get("/api/state").json()
        client.headers["X-CSRF-Token"] = state["csrf"]
        start(client)
        client.post("/api/question", json={"text": "这和身高有关吗？"})
        turn = client.post("/api/teammate", json={}).json()["history"][-1]
        assert turn["question"] == "这与时间有关吗？"
        assert turn["target"] == "" and turn["rationale"] == ""


def test_teammate_yield_is_a_model_error_but_not_a_request_failure():
    assert issubclass(DuplicateQuestion, ModelError)
    with pytest.raises(DuplicateQuestion):
        raise DuplicateQuestion("示例")
