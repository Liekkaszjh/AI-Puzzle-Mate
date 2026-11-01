"""标准库端到端测试：python -B -m unittest -v test_game.py"""

import http.cookiejar
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
import tempfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from llm import ModelClient, ModelError, parse_json_object
from module1_puzzles import DEMO_PUZZLES, choose_existing, generate_puzzle, save_generated, validate_generated
from module2_teammate import propose_question
from module3_host import judge, score_reconstruction
from module4_frontend import create_server


class DemoGameTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"DEMO_MODE": "true"}):
            self.client = ModelClient()
        self.server = create_server(self.client, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_port
        self.browser = self.new_browser()
        _, self.state = self.request("/api/state")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @staticmethod
    def new_browser():
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, data=None, browser=None, csrf=True):
        headers = {}
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
            if csrf:
                headers["X-CSRF-Token"] = self.state["csrf"]
        request = urllib.request.Request(self.base + path, data=body, headers=headers)
        try:
            response = (browser or self.browser).open(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.code, json.load(response)

    def start(self):
        code, self.state = self.request("/api/new", {})
        self.assertEqual(code, 200)
        return self.state

    def test_full_game_and_answer_secrecy(self):
        state = self.start()
        self.assertNotIn("solution", state)
        self.assertEqual(set(state["puzzle"]), {"title", "surface", "fact_count"})
        self.assertEqual(state["puzzle"]["fact_count"], 3)
        self.assertIsNone(state["report"])
        code, _ = self.request("/api/teammate", {})
        self.assertEqual(code, 409)
        code, state = self.request("/api/question", {"text": "这和年龄有关吗？"})
        self.assertEqual(code, 200)
        self.assertEqual(state["next_actor"], "teammate")
        code, state = self.request("/api/teammate", {})
        self.assertEqual(code, 200)
        self.assertEqual(state["history"][1]["actor"], "teammate")
        self.assertEqual(state["history"][1]["verdict"], "正确")
        self.assertEqual(state["next_actor"], "player")
        if "电梯" in state["puzzle"]["surface"]:
            answer = "他个子矮，够不到二十楼按钮。晴天先到十五楼走楼梯，下雨带伞可以用伞按按钮。"
        else:
            answer = "这是音箱里的钢琴录音，设置了八点定时播放，邻居出差忘了关闭。"
        code, state = self.request("/api/final", {"text": answer})
        self.assertEqual(code, 200)
        self.assertEqual(state["status"], "won")
        self.assertIn("bottom", state["solution"])
        code, _ = self.request("/api/question", {"text": "还能问吗？"})
        self.assertEqual(code, 409)

    def test_reveal_refresh_and_new_game(self):
        self.start()
        code, revealed = self.request("/api/reveal", {})
        self.assertEqual(code, 200)
        self.assertEqual(revealed["status"], "revealed")
        _, restored = self.request("/api/state")
        self.assertEqual(restored["solution"], revealed["solution"])
        fresh = self.start()
        self.assertNotEqual(fresh["puzzle"]["title"], revealed["puzzle"]["title"])
        self.assertNotIn("solution", fresh)
        self.assertEqual(fresh["history"], [])

    def test_sessions_and_csrf(self):
        self.start()
        other = self.new_browser()
        _, state = self.request("/api/state", browser=other)
        self.assertEqual(state["status"], "idle")
        self.assertNotEqual(state["csrf"], self.state["csrf"])
        code, _ = self.request("/api/reveal", {}, browser=other)
        self.assertEqual(code, 403)
        code, _ = self.request("/api/reveal", {}, csrf=False)
        self.assertEqual(code, 403)

    def test_input_validation_and_early_question(self):
        code, _ = self.request("/api/question", {"text": "可以开始吗？"})
        self.assertEqual(code, 409)
        self.start()
        for invalid in ("", "  ", "问" * 301, 123, ["问题"]):
            code, _ = self.request("/api/question", {"text": invalid})
            self.assertEqual(code, 400)
        code, _ = self.request("/api/new", [])
        self.assertEqual(code, 400)
        _, state = self.request("/api/state")
        self.assertEqual(state["history"], [])

    def test_upstream_failure_is_atomic(self):
        before = self.start()
        with patch("module4_frontend.server.choose_existing", side_effect=ModelError("抽题失败")):
            code, _ = self.request("/api/new", {})
            self.assertEqual(code, 502)
        with patch("module4_frontend.server.judge", side_effect=ModelError("判题失败")):
            code, _ = self.request("/api/question", {"text": "年龄有关吗？"})
            self.assertEqual(code, 502)
        _, after = self.request("/api/state")
        self.assertEqual(before, after)

    def test_busy_session_and_turn_limit(self):
        self.start()
        session = next(iter(self.server.sessions.values()))
        with session.lock:
            code, _ = self.request("/api/teammate", {})
            self.assertEqual(code, 409)
        session.history = [{"actor": "player", "kind": "question", "question": "身高有关吗？", "verdict": "正确", "feedback": ""}] * 200
        code, _ = self.request("/api/question", {"text": "还有吗？"})
        self.assertEqual(code, 409)
        code, state = self.request("/api/reveal", {})
        self.assertEqual(code, 200)
        self.assertEqual(state["status"], "revealed")

    def test_all_demo_teammate_questions_have_consistent_answers(self):
        for puzzle in DEMO_PUZZLES:
            history = []
            for _ in range(4):
                question = propose_question(self.client, puzzle["surface"], history)
                self.assertNotIn(question, [turn["question"] for turn in history])
                result = judge(self.client, puzzle, question)
                self.assertEqual(result["verdict"], "正确", question)
                history.append({"question": question, **result})
            with self.assertRaises(ModelError):
                propose_question(self.client, puzzle["surface"], history)

    def test_static_assets(self):
        for path, mime in (("/", "text/html"), ("/app.js", "text/javascript"), ("/styles.css", "text/css"), ("/host.svg", "image/svg+xml"), ("/player.svg", "image/svg+xml"), ("/teammate.svg", "image/svg+xml")):
            with self.browser.open(self.base + path, timeout=5) as response:
                self.assertIn(mime, response.headers["Content-Type"])
                self.assertGreater(len(response.read()), 100)
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        code, _ = self.request("/.env")
        self.assertEqual(code, 404)

    def test_solo_mode_never_requests_teammate(self):
        code, state = self.request("/api/new", {"play_mode": "solo"})
        self.assertEqual(code, 200)
        self.assertEqual(state["play_mode"], "solo")
        for _ in range(3):
            code, state = self.request("/api/question", {"text": "年龄有关吗？"})
            self.assertEqual(code, 200)
            self.assertEqual(state["next_actor"], "player")
        code, _ = self.request("/api/teammate", {})
        self.assertEqual(code, 409)
        code, _ = self.request("/api/new", {"play_mode": "invalid"})
        self.assertEqual(code, 400)

    def test_alternation_is_enforced_and_survives_refresh(self):
        self.start()
        for _ in range(3):
            code, state = self.request("/api/question", {"text": "年龄有关吗？"})
            self.assertEqual(code, 200)
            self.assertEqual(state["next_actor"], "teammate")
            code, _ = self.request("/api/question", {"text": "再问一个？"})
            self.assertEqual(code, 409)
            code, _ = self.request("/api/final", {"text": "先提交？"})
            self.assertEqual(code, 409)
            _, restored = self.request("/api/state")
            self.assertEqual(restored["next_actor"], "teammate")
            code, state = self.request("/api/teammate", {})
            self.assertEqual(code, 200)
            self.assertEqual(state["next_actor"], "player")
        self.assertEqual([turn["actor"] for turn in state["history"]], ["player", "teammate"] * 3)

    def test_teammate_judgment_retry_keeps_question_and_player_history(self):
        self.start()
        self.request("/api/question", {"text": "年龄有关吗？"})
        with patch("module4_frontend.server.propose_question", return_value="与身高有关吗？") as propose:
            with patch("module4_frontend.server.judge", side_effect=ModelError("判题失败")):
                code, _ = self.request("/api/teammate", {})
                self.assertEqual(code, 502)
            _, state = self.request("/api/state")
            self.assertEqual(len(state["history"]), 1)
            self.assertEqual(state["next_actor"], "teammate")
            self.assertEqual(state["pending_question"], "与身高有关吗？")
            code, state = self.request("/api/teammate", {})
            self.assertEqual(code, 200)
            self.assertEqual(len(state["history"]), 2)
            self.assertEqual(state["next_actor"], "player")
            self.assertIsNone(state["pending_question"])
            self.assertEqual(propose.call_count, 1)

    def test_demo_exhaustion_returns_control_to_player(self):
        self.start()
        for _ in range(5):
            self.request("/api/question", {"text": "年龄有关吗？"})
            code, state = self.request("/api/teammate", {})
            self.assertEqual(code, 200)
        self.assertEqual(state["next_actor"], "player")
        self.assertTrue(state["notice"])
        self.assertEqual(len(state["history"]), 9)

    def test_submission_scores_and_ends_game(self):
        self.start()
        code, state = self.request("/api/final", {"text": "他喜欢吃苹果，所以回家了。"})
        self.assertEqual(code, 200)
        self.assertEqual(state["status"], "scored")
        self.assertEqual(state["report"]["score"], 0)
        self.assertEqual(state["report"]["total_facts"], 3)
        self.assertIn("solution", state)
        self.assertEqual(len(state["report"]["facts"]), 3)
        code, _ = self.request("/api/final", {"text": "再交一次"})
        self.assertEqual(code, 409)
        _, restored = self.request("/api/state")
        self.assertEqual(restored["report"], state["report"])
        fresh = self.start()
        self.assertIsNone(fresh["report"])

    def test_new_source_requires_key_and_theme(self):
        self.start()
        code, _ = self.request("/api/new", {"source": "new", "theme": "校园"})
        self.assertEqual(code, 400)
        code, _ = self.request("/api/new", {"source": "invalid"})
        self.assertEqual(code, 400)

    def test_existing_source_makes_no_generation_call(self):
        with patch("module4_frontend.server.generate_puzzle") as generate:
            state = self.start()
        generate.assert_not_called()
        self.assertEqual(state["source"], "existing")

    def test_demo_partial_and_complete_scores(self):
        elevator, recording = DEMO_PUZZLES
        partial = score_reconstruction(self.client, elevator, "这个人身材矮小，够不到二十楼的按钮。")
        self.assertGreater(partial["score"], 0)
        self.assertLess(partial["score"], 100)
        self.assertEqual(partial["facts"][0]["status"], "matched")
        for puzzle in (elevator, recording):
            report = score_reconstruction(self.client, puzzle, puzzle["bottom"])
            self.assertEqual(report["score"], 100)

    def test_scoring_failure_preserves_current_game(self):
        before = self.start()
        with patch("module4_frontend.server.judge", side_effect=ModelError("评分失败")):
            code, _ = self.request("/api/final", {"text": "我还原的故事"})
        self.assertEqual(code, 502)
        _, after = self.request("/api/state")
        self.assertEqual(before, after)


class ModelProtocolTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.response_mode = "valid"
        owner = self

        class Stub(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                payload = json.loads(request["messages"][1]["content"])
                owner.calls.append({"path": self.path, "auth": self.headers["Authorization"], "request": request, "payload": payload})
                if owner.response_mode == "401":
                    self.send_response(401)
                    self.end_headers()
                    return
                if "theme" in payload:
                    content = {"title": "模拟测试题", "surface": "这是公开汤面。", "bottom": "这是保密汤底：定时音箱。", "key_points": ["录音", "定时播放", "忘了关闭"]}
                elif "surface" in payload:
                    content = {"question": "这和录音有关吗？"}
                elif "kind" not in payload:
                    content = {"facts": [{"index": 0, "status": "matched", "reason": "答案明确提到录音"}, {"index": 1, "status": "partial", "reason": "提到播放，未说明定时"}, {"index": 2, "status": "missing", "reason": "未提到关闭"}]}
                else:
                    content = {"verdict": "正确", "feedback": "这是不应该暴露的秘密答案"}
                text = json.dumps(content, ensure_ascii=False) if owner.response_mode != "invalid" else "不是 JSON"
                result = {"choices": [{"message": {"content": "```json\n" + text + "\n```"}}]}
                if owner.response_mode == "truncated":
                    result["choices"][0]["finish_reason"] = "length"
                if owner.response_mode == "empty":
                    result["choices"][0]["message"] = {"content": "", "reasoning_content": "internal reasoning"}
                body = json.dumps(result).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        with patch.dict(os.environ, {"DEMO_MODE": "false", "DEEPSEEK_API_KEY": "test-local-key", "DEEPSEEK_TIMEOUT": "5"}):
            self.client = ModelClient()
        self.assertEqual(self.client.base_url, "https://api.deepseek.com/v1")
        self.assertEqual(self.client.model, "deepseek-flash")
        # 仅测试时将 HTTP 请求指向本地模拟服务，不请求真实 DeepSeek。
        self.client.base_url = "http://127.0.0.1:%d/v1" % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_single_calls_and_module_boundaries(self):
        puzzle = generate_puzzle(self.client, "测试")
        question = propose_question(self.client, puzzle["surface"], [])
        result = judge(self.client, puzzle, question)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(set(self.calls[1]["payload"]), {"surface", "history"})
        self.assertNotIn(puzzle["bottom"], json.dumps(self.calls[1], ensure_ascii=False))
        self.assertEqual(self.calls[2]["payload"]["bottom"], puzzle["bottom"])
        self.assertEqual(result, {"verdict": "正确", "feedback": ""})
        for call in self.calls:
            self.assertEqual(call["path"], "/v1/chat/completions")
            self.assertEqual(call["auth"], "Bearer test-local-key")
            self.assertEqual(call["request"]["model"], "deepseek-flash")
            self.assertEqual(call["request"]["response_format"], {"type": "json_object"})
            self.assertEqual(call["request"]["thinking"], {"type": "disabled"})
            self.assertIs(call["request"]["stream"], False)

    def test_invalid_response_does_not_retry(self):
        self.response_mode = "invalid"
        with self.assertRaises(ModelError):
            generate_puzzle(self.client)
        self.assertEqual(len(self.calls), 1)

    def test_truncation_and_empty_response_have_specific_errors(self):
        for mode, expected in (("truncated", "截断"), ("empty", "正文")):
            self.response_mode = mode
            self.calls.clear()
            with self.assertRaises(ModelError) as caught:
                generate_puzzle(self.client)
            self.assertIn(expected, str(caught.exception))
            self.assertEqual(len(self.calls), 1)

    def test_strict_json_rejects_duplicates_constants_and_mixed_text(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '说明：{"x":1}', '{"x":', '[]'):
            with self.assertRaises(ModelError):
                parse_json_object(text)
        self.assertEqual(parse_json_object('```json\n{"x":1}\n```'), {"x": 1})

    def test_generated_contract_enforces_short_surface_and_unique_facts(self):
        valid = {"title": "新题", "surface": "这是一个有具体异常的故事。", "bottom": "完整真相。", "key_points": ["原因事实", "手段事实", "结果事实"]}
        self.assertEqual(len(validate_generated(valid)["key_points"]), 3)
        invalid = [dict(valid, surface="字" * 101), dict(valid, surface="第一段\n第二段"), dict(valid, key_points=["事实一", "事实一。", "事实二"]), dict(valid, key_points=["事实一", "事实二"]), dict(valid, extra="多余字段")]
        for candidate in invalid:
            with self.assertRaises(ModelError):
                validate_generated(candidate)

    def test_fact_scoring_uses_one_call_and_calculates_score_in_python(self):
        puzzle = generate_puzzle(self.client)
        self.calls.clear()
        report = score_reconstruction(self.client, puzzle, "录音在播放")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(report["score"], 50)
        self.assertEqual(report["matched_count"], 1)
        self.assertEqual(report["total_facts"], 3)

    def test_invalid_fact_reports_are_rejected(self):
        puzzle = generate_puzzle(self.client)
        valid = [{"index": 0, "status": "matched", "reason": "匹配"}, {"index": 1, "status": "missing", "reason": "遗漏"}]
        bad_reports = [[], valid[:1], [valid[1], valid[0]], [{"index": 0, "status": [], "reason": "无效状态"}, valid[1]], [{"index": True, "status": "matched", "reason": "无效序号"}, valid[1]]]
        for facts in bad_reports:
            with patch.object(self.client, "complete_json", return_value={"facts": facts}):
                with self.assertRaises(ModelError):
                    score_reconstruction(self.client, puzzle, "答案")

    def test_generated_library_persists_and_can_be_selected(self):
        puzzle = generate_puzzle(self.client, "校园")
        with tempfile.TemporaryDirectory() as temporary:
            with patch("module1_puzzles.LIBRARY_PATH", Path(temporary) / "puzzles.json"):
                save_generated(puzzle)
                with patch("module1_puzzles.random.choice", side_effect=lambda items: items[-1]):
                    selected = choose_existing(self.client)
                self.assertEqual(selected["id"], puzzle["id"])
                self.assertEqual(selected["key_points"], puzzle["key_points"])

    def test_new_game_route_generates_saves_and_hides_facts(self):
        server = create_server(self.client, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        browser = DemoGameTests.new_browser()
        base = "http://127.0.0.1:%d" % server.server_port
        try:
            with browser.open(base + "/api/state") as response:
                state = json.load(response)
            with tempfile.TemporaryDirectory() as temporary:
                with patch("module1_puzzles.LIBRARY_PATH", Path(temporary) / "puzzles.json"):
                    request = urllib.request.Request(base + "/api/new", data=json.dumps({"source": "new", "theme": "校园", "play_mode": "solo"}).encode(), headers={"Content-Type": "application/json", "X-CSRF-Token": state["csrf"]})
                    with browser.open(request) as response:
                        result = json.load(response)
                    self.assertEqual(result["source"], "new")
                    self.assertEqual(result["status"], "playing")
                    self.assertEqual(result["puzzle"]["fact_count"], 3)
                    self.assertNotIn("key_points", result["puzzle"])
                    self.assertTrue((Path(temporary) / "puzzles.json").exists())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_upstream_error_hides_credentials(self):
        self.response_mode = "401"
        with self.assertRaises(ModelError) as caught:
            generate_puzzle(self.client)
        self.assertIn("API Key 无效", str(caught.exception))
        self.assertNotIn("test-local-key", str(caught.exception))
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
