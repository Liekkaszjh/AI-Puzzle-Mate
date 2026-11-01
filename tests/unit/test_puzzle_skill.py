import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from puzzle_fixtures import PUZZLE, REQUEST, ScriptedModel
from puzzle_generator import PuzzleError, PuzzleService
from puzzle_generator.prompts import generation_messages, review_messages
from puzzle_generator.skill_loader import load_puzzle_skill


class PuzzleSkillTests(unittest.TestCase):
    def test_bundled_skill_body_is_readable(self):
        body = load_puzzle_skill()
        self.assertIn("consistency", body)
        self.assertNotIn("description:", body)

    def test_generation_and_review_use_same_skill(self):
        with patch("puzzle_generator.prompts.load_puzzle_skill", return_value="测试出题规则"):
            generation = generation_messages(REQUEST, ["上次问题"])
            review = review_messages(PUZZLE, REQUEST)
        for messages in (generation, review):
            self.assertIn("测试出题规则", messages[0]["content"])
        self.assertEqual(json.loads(generation[1]["content"])["previous_issues"], ["上次问题"])

    def test_edits_are_loaded_without_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "skills" / "puzzle-authoring" / "SKILL.md"
            path.parent.mkdir(parents=True)
            with patch("puzzle_generator.skill_loader.files", return_value=root):
                for body in ("规则一", "规则二"):
                    path.write_text("---\nname: puzzle-authoring\n---\n" + body, encoding="utf-8")
                    self.assertEqual(load_puzzle_skill(), body)

    def test_invalid_skill_reports_controlled_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "skills" / "puzzle-authoring" / "SKILL.md"
            path.parent.mkdir(parents=True)
            with patch("puzzle_generator.skill_loader.files", return_value=root):
                for content in ("没有元信息", "---\n没有结束标记", "---\nname: test\n---\n"):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(PuzzleError) as raised:
                        load_puzzle_skill()
                    self.assertEqual(raised.exception.code, "SKILL_INVALID")

    def test_missing_skill_stops_before_model_call(self):
        with tempfile.TemporaryDirectory() as directory:
            model = ScriptedModel([])
            with patch("puzzle_generator.skill_loader.files", return_value=Path(directory)):
                result = PuzzleService(model).generate(REQUEST)
        self.assertEqual(result["error"]["code"], "SKILL_LOAD_FAILED")
        self.assertEqual(model.calls, [])
