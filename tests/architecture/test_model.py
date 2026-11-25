import io
import json

import pytest

from llm import ModelClient, ModelError, parse_json_object
from engine import AgentEngine


def test_deepseek_request_format_and_truncated_response(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    captured = []
    finish_reason = "stop"

    def open_request(request, timeout):
        captured.append(request)
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": finish_reason, "message": {"content": '{"question":"有关吗？"}'}}]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    client = ModelClient()
    assert client.complete_json("测试", {"surface": "汤面"}) == {"question": "有关吗？"}
    request = captured[0]
    body = json.loads(request.data)
    assert request.full_url == "https://api.deepseek.com/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer test-only-key"
    assert body["response_format"] == {"type": "json_object"}
    assert body["stream"] is False
    finish_reason = "length"
    with pytest.raises(ModelError, match="截断"):
        client.complete_json("测试", {})
    assert len(captured) == 2  # no hidden retries


@pytest.mark.parametrize("content", ['{"x":1,"x":2}', '{"x":NaN}', '解释 {"x":1}', '[1]', '{"x":'])
def test_strict_json(content):
    with pytest.raises(ModelError):
        parse_json_object(content)


def test_teammate_gets_only_public_data_and_score_is_calculated_locally():
    class Model:
        demo = False
        calls = []
        prompts = []

        def complete_json(self, system, payload, max_tokens=1200):
            self.calls.append(payload)
            self.prompts.append(system)
            if "surface" in payload:
                return {"question": "与录音有关吗？", "target": "录音", "rationale": "先确认声源是不是设备"}
            return {"facts": [{"index": 0, "status": "matched", "reason": "提及录音"}, {"index": 1, "status": "partial", "reason": "未说明时间"}, {"index": 2, "status": "missing", "reason": "未提及"}]}

    model = Model()
    engine = AgentEngine(model)
    assert engine.teammate("公开故事", []) == {"question": "与录音有关吗？", "target": "录音",
                                             "rationale": "先确认声源是不是设备"}
    # 只公开汤面、公开问答与公开黑板进入模型；汤底、关键事实、数据库对象都不在 payload 里。
    assert set(model.calls[0]) == {"surface", "history", "avoid", "you", "board", "focus_dimension"}
    assert model.calls[0]["surface"] == "公开故事"
    assert model.calls[0]["board"]["confirmed"] == []
    assert model.calls[0]["focus_dimension"] == "人物"  # 小夏负责人物/物品
    from module2_teammate import TEAMMATES
    assert engine.teammate("公开故事", [], TEAMMATES[1])["question"] == "与录音有关吗？"
    assert model.calls[1]["you"]["name"] == "阿澄"
    assert "因果推理" in model.prompts[1]
    result = engine.score({"bottom": "私有真相", "key_points": ["录音", "定时", "忘关"]}, "录音播放")
    assert result["report"]["score"] == 50
