import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from puzzle_fixtures import APPROVED, PUZZLE, ScriptedModel
from puzzle_generator import PuzzleError
from puzzle_generator.cli import main, save_report
from puzzle_generator.config import ModelSettings, load_env_file


class ConfigTests(unittest.TestCase):
    def test_dotenv_bom_quotes_comments_and_environment_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('\ufeff# comment\nA=file\nB="value#hash" # comment\nexport C= plain # note\nD=\n', encoding="utf-8")
            env = {"A": "existing"}
            load_env_file(path, env)
            self.assertEqual(env, {"A": "existing", "B": "value#hash", "C": "plain", "D": ""})

    def test_invalid_dotenv_is_atomic_and_hides_values(self):
        with tempfile.TemporaryDirectory() as directory:
            for content in ('A=ok\nbroken secret', 'A="secret', 'A="secret" trailing'):
                path = Path(directory) / ".env"
                path.write_text(content, encoding="utf-8")
                env = {}
                with self.assertRaises(PuzzleError) as caught:
                    load_env_file(path, env)
                self.assertEqual(env, {})
                self.assertNotIn("secret", str(caught.exception))

    def test_missing_env_file(self):
        with self.assertRaises(PuzzleError):
            load_env_file(Path(tempfile.gettempdir()) / "missing-puzzle-config-42.env", {})

    def test_settings_converts_milliseconds_and_hides_key(self):
        settings = ModelSettings.from_env({"PUZZLE_MODEL_ENDPOINT": "https://model.example/chat/completions",
                                          "PUZZLE_MODEL_NAME": "test", "PUZZLE_MODEL_API_KEY": "secret",
                                          "PUZZLE_MODEL_TIMEOUT_MS": "120000"})
        self.assertEqual(settings.timeout_seconds, 120)
        self.assertEqual(settings.api_key, "secret")
        self.assertNotIn("secret", repr(settings))

    def test_invalid_settings(self):
        base = {"PUZZLE_MODEL_ENDPOINT": "https://model.example", "PUZZLE_MODEL_NAME": "test"}
        for env in ({}, {**base, "PUZZLE_MODEL_NAME": ""},
                    *[{**base, "PUZZLE_MODEL_TIMEOUT_MS": value} for value in ("0", "nan", "-1", "1.5", "3600001")]):
            with self.assertRaises(PuzzleError):
                ModelSettings.from_env(env)


class CliTests(unittest.TestCase):
    def test_save_report_preserves_full_unicode_json_and_unique_names(self):
        with tempfile.TemporaryDirectory() as directory:
            result = {"success": True, "puzzle": PUZZLE, "review": APPROVED}
            first = save_report(result, Path(directory))
            second = save_report(result, Path(directory))
            self.assertNotEqual(first, second)
            self.assertEqual(json.loads(first.read_text(encoding="utf-8")), result)
            self.assertIn("校园", first.read_text(encoding="utf-8"))

    def test_live_cli_success_uses_existing_env_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("PUZZLE_MODEL_ENDPOINT=https://model.example/chat/completions\nPUZZLE_MODEL_NAME=test\nPUZZLE_MODEL_TIMEOUT_MS=120000\n", encoding="utf-8")
            output = Path(directory) / "results"
            with patch.dict("os.environ", {}, clear=True), patch("puzzle_generator.cli.ChatModelClient", return_value=ScriptedModel([PUZZLE, APPROVED])) as factory:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = main(["校园", "普通", "--env-file", str(env_file), "--output-dir", str(output)])
            self.assertEqual(code, 0)
            self.assertEqual(factory.call_args.kwargs["timeout_seconds"], 120)
            report = json.loads(next(output.glob("*.json")).read_text(encoding="utf-8"))
            self.assertTrue(report["success"])
            self.assertEqual(report["puzzle"]["solution"], PUZZLE["solution"])

    def test_live_cli_failure_report_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {"PUZZLE_MODEL_ENDPOINT": "https://model.example/chat/completions", "PUZZLE_MODEL_NAME": "test"}
            with patch.dict("os.environ", env, clear=True), patch("puzzle_generator.cli.ChatModelClient", return_value=ScriptedModel([{}])):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = main(["--max-retries", "0", "--output-dir", directory], default_env_file=Path(directory) / ".env")
            self.assertEqual(code, 1)
            report = json.loads(next(Path(directory).glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(report["error"]["code"], "QUALITY_RETRY_EXHAUSTED")
            self.assertNotIn("puzzle", report)

    def test_missing_configuration_never_constructs_client(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {}, clear=True), patch("puzzle_generator.cli.ChatModelClient") as factory:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = main([], default_env_file=Path(directory) / ".env")
            self.assertEqual(code, 1)
            factory.assert_not_called()

    def test_cli_defaults_to_three_retries_and_displays_each_round(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {"PUZZLE_MODEL_ENDPOINT": "https://model.example/chat/completions", "PUZZLE_MODEL_NAME": "test"}
            model = ScriptedModel([{}, {}, {}, {}])
            console = io.StringIO()
            with patch.dict("os.environ", env, clear=True), patch("puzzle_generator.cli.ChatModelClient", return_value=model):
                with contextlib.redirect_stdout(console):
                    code = main(["--output-dir", directory], default_env_file=Path(directory) / ".env")
            self.assertEqual(code, 1)
            self.assertEqual(len(model.calls), 4)
            self.assertIn("第1/4轮", console.getvalue())
            self.assertIn("第4/4轮", console.getvalue())
            report = json.loads(next(Path(directory).glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(report["attempts"], 4)


if __name__ == "__main__":
    unittest.main()
