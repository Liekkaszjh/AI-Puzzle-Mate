import pytest
from fastapi.testclient import TestClient

from engine import AgentEngine
from llm import ModelClient
from module1_puzzles.puzzles import DEMO_PUZZLES
from module2_teammate import PROFILES, TEAMMATES, propose_turn
from module2_teammate.board import (classify, hint, new_board, next_focus, open_dimensions,
                                    record_turn, restore_board, summary, view)
from module3_host.api.app import create_app


class DemoClient:
    demo = True


def test_classify_maps_targets_to_dimensions():
    assert classify("身高") == "人物"
    assert classify("按钮高度") == "物品"
    assert classify("定时播放") == "时间"
    assert classify("忘关设备") == "因果"
    assert classify("完全无关的短语") is None
    assert classify(None) is None


def test_record_turn_tracks_confirmed_excluded_and_stall():
    board = new_board()
    record_turn(board, {"question": "这与身高有关吗？", "verdict": "正确", "target": "身高"})
    assert board["confirmed"] == ["这与身高有关吗？"]
    assert board["covered"]["人物"] == 1
    record_turn(board, {"question": "这与年龄有关吗？", "verdict": "无关", "target": "年龄"})
    record_turn(board, {"question": "这与职业有关吗？", "verdict": "无关", "target": "职业"})
    assert board["stalled"] == 2
    record_turn(board, {"question": "他带的是雨伞吗？", "verdict": "错误", "target": "雨伞"})
    assert board["excluded"] == ["他带的是雨伞吗？"]
    assert board["stalled"] == 0  # 排除也是新信息，不算停滞


def test_focus_follows_profile_dimensions_until_covered():
    board = new_board()
    detail, causal = PROFILES[0], PROFILES[1]
    assert next_focus(board, detail) == "人物"
    assert open_dimensions(board, detail) == ["人物", "物品"]
    record_turn(board, {"question": "身高？", "verdict": "正确", "target": "身高"})
    assert next_focus(board, detail) == "物品"
    record_turn(board, {"question": "雨伞？", "verdict": "正确", "target": "雨伞"})
    assert next_focus(board, detail) is None
    assert next_focus(board, causal) == "时间"


def test_legacy_or_missing_board_restores_without_migration():
    assert restore_board(None)["covered"] == {dimension: 0 for dimension in ("人物", "物品", "时间", "因果", "动机", "反例")}
    partial = restore_board({"asked": 2, "confirmed": ["旧问题"]})
    assert partial["asked"] == 2 and partial["confirmed"] == ["旧问题"]
    assert partial["covered"]["人物"] == 0
    assert summary(None)["open_dimensions"] == ["人物", "物品", "时间", "因果", "动机", "反例"]
    assert view(None)["confirmed"] == 0


def test_demo_teammate_asks_inside_its_dimension_first():
    surface = DEMO_PUZZLES[1]["surface"]  # 录音题：声源/录音属物品，定时属时间，忘关属因果
    board = new_board()
    turn = propose_turn(DemoClient(), surface, [], TEAMMATES[1], board)  # 阿澄负责时间/因果
    assert classify(turn["target"]) == "时间"
    # 该维度没有对应线索时退回轮换顺序，不硬凑别的题的答案。
    elevator = DEMO_PUZZLES[0]["surface"]
    fallback = propose_turn(DemoClient(), elevator, [], TEAMMATES[1], board)
    assert classify(fallback["target"]) in ("人物", "物品")


def test_hint_reports_convergence_and_stall():
    board = new_board()
    assert hint(board, 3) == ""
    for index in range(3):
        record_turn(board, {"question": "q%d" % index, "verdict": "正确", "target": "身高"})
    assert "提交完整还原" in hint(board, 3)

    stalled = new_board()
    for index in range(3):
        record_turn(stalled, {"question": "s%d" % index, "verdict": "无关", "target": "身高"})
    assert "换个维度" in hint(stalled, 3)


@pytest.fixture
def demo_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    engine = AgentEngine(ModelClient())
    with TestClient(create_app(tmp_path / "board.sqlite3", engine)) as client:
        state = client.get("/api/state").json()
        client.headers["X-CSRF-Token"] = state["csrf"]
        yield client


def test_state_exposes_board_and_convergence_hint(demo_client):
    state = demo_client.post("/api/new", json={"source": "existing", "play_mode": "coop", "theme": ""}).json()
    assert state["board"]["asked"] == 0 and state["hint"] == ""
    for _ in range(3):
        demo_client.post("/api/question", json={"text": "这和身高有关吗？"})
        while demo_client.get("/api/state").json()["next_actor"] == "teammate":
            demo_client.post("/api/teammate", json={})
    state = demo_client.get("/api/state").json()
    assert state["board"]["asked"] == len(state["history"]) - 3
    assert state["board"]["confirmed"] >= 3
    assert state["board"]["latest_confirmed"]
    assert "提交完整还原" in state["hint"]
