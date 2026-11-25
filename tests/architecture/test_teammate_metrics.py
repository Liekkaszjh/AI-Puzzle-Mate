import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_script():
    path = ROOT / "scripts/evaluate_teammates.py"
    spec = importlib.util.spec_from_file_location("evaluate_teammates", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evaluation_script_meets_its_baseline_offline(capsys, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    module = load_script()
    code = module.main(["--json", "--games", "2"])
    metrics = json.loads(capsys.readouterr().out)
    assert code == 0
    assert metrics["mode"] == "demo"
    assert metrics["teammate_turns"] == 8  # 两题各 2 位队友 × 4 条演示线索
    assert metrics["repeat_rate"] == 0
    assert metrics["failures"] == []
