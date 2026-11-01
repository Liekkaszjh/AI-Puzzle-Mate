import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import UUID

from puzzle_fixtures import APPROVED, PUZZLE, REQUEST, ScriptedModel
from puzzle_generator import PuzzleChecker, PuzzleError, PuzzleService, check_structure
from puzzle_generator.contracts import parse_model_object
from puzzle_generator.hint_rules import build_first_hint, check_first_hint


class PuzzleServiceTests(unittest.TestCase):
    def test_success_defaults_and_field_filtering(self):
        model = ScriptedModel([{**PUZZLE, "extra": "忽略"}, APPROVED])
        result = PuzzleService(model).generate({"theme": " 校园 "})
        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 1)
        UUID(result["puzzle"]["id"])
        self.assertNotIn("extra", result["puzzle"])
        self.assertEqual(result["puzzle"]["difficulty"], "普通")
        self.assertEqual(len(model.calls), 2)

    def test_invalid_request_never_calls_model(self):
        inputs = [None, {}, [], {"theme": " "}, {"theme": "校" * 51},
                  {"theme": "校园", "difficulty": []}, {"theme": "校园", "difficulty": "unknown"}]
        for value in inputs:
            with self.subTest(value=value):
                model = ScriptedModel([])
                result = PuzzleService(model).generate(value)
                self.assertEqual(result["error"]["code"], "INVALID_REQUEST")
                self.assertEqual(result["attempts"], 0)
                self.assertEqual(model.calls, [])

    def test_structure_checked_before_model_review(self):
        checker = PuzzleChecker(ScriptedModel([]))
        for draft in [None, {}, {**PUZZLE, "hints": ["一", "二"]}, {**PUZZLE, "key_facts": []},
                      {**PUZZLE, "clues": [1]}, {**PUZZLE, "theme": "成长"}, {**PUZZLE, "difficulty": "困难"}]:
            with self.subTest(draft=draft):
                self.assertFalse(checker.check(draft, REQUEST)["passed"])

    def test_structure_issue_is_passed_to_regeneration(self):
        model = ScriptedModel([{**PUZZLE, "hints": []}, PUZZLE, APPROVED])
        result = PuzzleService(model).generate(REQUEST)
        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 2)
        self.assertIn("hints", "".join(json.loads(model.calls[1][1]["content"])["previous_issues"]))

    def test_quality_rejection_regenerates(self):
        rejected = deepcopy(APPROVED)
        rejected["checks"]["consistency"] = False
        rejected["issues"] = ["时间线冲突"]
        model = ScriptedModel([PUZZLE, rejected, PUZZLE, APPROVED])
        result = PuzzleService(model).generate(REQUEST)
        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(json.loads(model.calls[2][1]["content"])["previous_issues"], ["时间线冲突"])

    def test_four_candidates_at_most_and_no_failed_draft(self):
        model = ScriptedModel([{}, {}, {}, {}])
        result = PuzzleService(model).generate(REQUEST)
        self.assertEqual(result["attempts"], 4)
        self.assertEqual(len(model.calls), 4)
        self.assertEqual(result["error"]["code"], "QUALITY_RETRY_EXHAUSTED")
        self.assertNotIn("puzzle", result)

    def test_invalid_generation_json_and_disabled_retries(self):
        model = ScriptedModel(["invalid JSON", PUZZLE, APPROVED])
        self.assertTrue(PuzzleService(model).generate(REQUEST)["success"])
        result = PuzzleService(ScriptedModel([{}]), max_retries=0).generate(REQUEST)
        self.assertEqual(result["attempts"], 1)

    def test_invalid_review_stops_immediately(self):
        for review in ["invalid JSON", {"checks": {}}, {**APPROVED, "checks": {**APPROVED["checks"], "safety": "true"}}]:
            model = ScriptedModel([PUZZLE, review])
            result = PuzzleService(model).generate(REQUEST)
            self.assertEqual(result["error"]["code"], "REVIEW_INVALID")
            self.assertEqual(result["attempts"], 1)
            self.assertNotIn("puzzle", result)

    def test_every_review_check_can_block(self):
        for name in APPROVED["checks"]:
            review = deepcopy(APPROVED)
            review["checks"][name] = False
            result = PuzzleService(ScriptedModel([PUZZLE, review]), max_retries=0).generate(REQUEST)
            self.assertFalse(result["success"])
            self.assertIn(name, result["error"]["issues"][0])

    def test_duplicates_ignore_whitespace_and_punctuation(self):
        for field in ("key_facts", "clues", "hints"):
            values = [PUZZLE[field][0], f" {PUZZLE[field][0]}。 "]
            if field == "hints":
                values.append("第三条")
            result = PuzzleChecker(ScriptedModel([])).check({**PUZZLE, field: values}, REQUEST)
            self.assertIn("重复", "".join(result["issues"]))

    def test_duplicates_preserve_meaningful_symbols(self):
        self.assertEqual(check_structure({**PUZZLE, "key_facts": ["A+B", "A-B"]}, REQUEST), [])

    def test_first_hint_cannot_add_hidden_mechanism(self):
        hints = [
            "说明有人一直在为某个人保留进度",
            "请留意汤面中的“有人一直在为某个人保留进度”。",
            "请留意汤面中的“画纸上没有颜料”。说明有人用了剪刀。",
            "请留意汤面中的“”。",
        ]
        for hint in hints:
            with self.subTest(hint=hint):
                draft = {**PUZZLE, "hints": [hint, *PUZZLE["hints"][1:]]}
                result = PuzzleChecker(ScriptedModel([])).check(draft, REQUEST)
                self.assertFalse(result["passed"])
                self.assertIn("一级提示", "".join(result["issues"]))

    def test_generator_replaces_revealing_first_hint_with_public_excerpt(self):
        invalid = {**PUZZLE, "hints": ["说明有人一直在为某个人保留进度", *PUZZLE["hints"][1:]]}
        model = ScriptedModel([invalid, APPROVED])
        result = PuzzleService(model).generate(REQUEST)
        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(check_first_hint(PUZZLE["surface"], result["puzzle"]["hints"][0]), [])
        self.assertNotIn("保留进度", result["puzzle"]["hints"][0])
        self.assertEqual(result["puzzle"]["hints"][1:], PUZZLE["hints"][1:])

    def test_progress_reports_regeneration_and_acceptance(self):
        model = ScriptedModel([{}, PUZZLE, APPROVED])
        events = []
        result = PuzzleService(model).generate(REQUEST, on_progress=events.append)
        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 2)
        self.assertTrue(json.loads(model.calls[1][1]["content"])["previous_issues"])
        self.assertEqual([event["stage"] for event in events],
                         ["generating", "checking", "rejected", "generating", "checking", "accepted"])
        self.assertTrue(events[2]["will_retry"])

    def test_progress_stops_at_retry_limit_and_callback_failure_is_nonfatal(self):
        events = []
        result = PuzzleService(ScriptedModel([{}, {}, {}, {}])).generate(REQUEST, on_progress=events.append)
        self.assertFalse(result["success"])
        rejections = [event for event in events if event["stage"] == "rejected"]
        self.assertEqual([event["will_retry"] for event in rejections], [True, True, True, False])

        def broken_observer(event):
            raise RuntimeError("展示失败")

        result = PuzzleService(ScriptedModel([PUZZLE, APPROVED])).generate(REQUEST, on_progress=broken_observer)
        self.assertTrue(result["success"])

    def test_review_requires_evidence_and_valid_references(self):
        bad_links = [
            {**APPROVED["causal_links"][0], "fact_indices": [99]},
            {**APPROVED["causal_links"][0], "fact_indices": [True]},
            {**APPROVED["causal_links"][0], "surface_event": "不存在的原文"},
            {**APPROVED["causal_links"][0], "supported": 1},
        ]
        reviews = [{**APPROVED, "reasons": {}}, {**APPROVED, "causal_links": []},
                   {**APPROVED, "missing_premises": None}]
        reviews += [{**APPROVED, "causal_links": [link]} for link in bad_links]
        for review in reviews:
            with self.subTest(review=review):
                with self.assertRaises(PuzzleError) as caught:
                    PuzzleChecker(ScriptedModel([review])).check(PUZZLE, REQUEST)
                self.assertEqual(caught.exception.code, "REVIEW_INVALID")

    def test_missing_premises_override_all_true_and_regenerate(self):
        review = {**APPROVED, "missing_premises": ["缺少必要的材料变化说明"]}
        model = ScriptedModel([PUZZLE, review, PUZZLE, APPROVED])
        result = PuzzleService(model).generate(REQUEST)
        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 2)
        self.assertIn("必要前提", json.loads(model.calls[2][1]["content"])["previous_issues"][0])

    def test_unexplained_event_overrides_all_true(self):
        review = {**APPROVED, "causal_links": [{**APPROVED["causal_links"][0], "supported": False, "fact_indices": []}]}
        result = PuzzleChecker(ScriptedModel([review])).check(PUZZLE, REQUEST)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["consistency"])
        self.assertFalse(result["checks"]["solvability"])

    def test_student_causal_gap_regression(self):
        student = {**PUZZLE, "surface": "小周听不清老师的问题，却写答案给同桌代答。换到前排后他自己举手了。",
                   "solution": "小周听力不好，老师调他到前排就解决了问题。", "key_facts": ["小周听不清", "前排能听清"],
                   "hints": ["请留意汤面中的“却写答案给同桌代答”。", "获取问题的方式", "考虑听觉条件"]}
        review = {**APPROVED, "causal_links": [{"surface_event": "却写答案给同桌代答", "explanation": "未说明信息来源及代答原因。",
                   "fact_indices": [], "supported": False}], "missing_premises": ["获取问题的方式", "代答原因"]}
        result = PuzzleService(ScriptedModel([student, review]), max_retries=0).generate(REQUEST)
        self.assertFalse(result["success"])
        self.assertIn("代答", "".join(result["error"]["issues"]))
        self.assertNotIn("puzzle", result)

    def test_json_round_trip_and_timings_on_success_and_failure(self):
        success = PuzzleService(ScriptedModel([PUZZLE, APPROVED])).generate(REQUEST)
        restored = json.loads(json.dumps(success, ensure_ascii=False))
        for field in ("solution", "key_facts", "clues"):
            self.assertEqual(restored["puzzle"][field], PUZZLE[field])
        self.assertEqual(restored["puzzle"]["hints"], [build_first_hint(PUZZLE["surface"]), *PUZZLE["hints"][1:]])
        failure = PuzzleService(ScriptedModel([])).generate({})
        for result in (success, failure):
            for value in result["timings"].values():
                self.assertIs(type(value), int)
                self.assertGreaterEqual(value, 0)

    def test_model_error_stops_and_internal_details_are_hidden(self):
        model = ScriptedModel([PuzzleError("MODEL_TIMEOUT", "模型调用超时。")])
        self.assertEqual(PuzzleService(model).generate(REQUEST)["error"]["code"], "MODEL_TIMEOUT")
        broken = ScriptedModel([RuntimeError("secret API key")])
        result = PuzzleService(broken).generate(REQUEST)
        self.assertEqual(result["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("secret", json.dumps(result))

    def test_separate_models_and_concurrent_calls(self):
        class ConstantModel:
            def __init__(self, response):
                self.response = json.dumps(response, ensure_ascii=False)

            def complete(self, messages):
                return self.response

        service = PuzzleService(ConstantModel(PUZZLE), review_model=ConstantModel(APPROVED))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(service.generate, [REQUEST, REQUEST]))
        self.assertTrue(all(result["success"] and result["attempts"] == 1 for result in results))
        self.assertNotEqual(results[0]["puzzle"]["id"], results[1]["puzzle"]["id"])

    def test_invalid_configuration(self):
        for retries in (-1, 4, 0.5, True):
            with self.assertRaises(ValueError):
                PuzzleService(ScriptedModel([]), max_retries=retries)
        with self.assertRaises(TypeError):
            PuzzleService(object())

    def test_strict_json_parser(self):
        for text in ('[]', 'null', '{"number": NaN}', '```json\n{}\n```', '{} trailing'):
            with self.assertRaises(PuzzleError):
                parse_model_object(text)


if __name__ == "__main__":
    unittest.main()
