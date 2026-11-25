"""离线评测 AI 队友：问句重复率、判题无关率、确认覆盖与每回合模型调用数。

默认强制演示模式：不联网、不花钱、可重复。接真实模型时加 --live，并确保
.env 配置了 DEEPSEEK_API_KEY 且 DEMO_MODE=false。

用法：
  python scripts/evaluate_teammates.py
  python scripts/evaluate_teammates.py --games 4 --rounds 3 --json
  python scripts/evaluate_teammates.py --max-repeat-rate 0.05 --max-irrelevant-rate 0.4

退出码：指标满足阈值返回 0，否则 1，可直接当回归门禁。
"""

import argparse
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

PLAYER_QUESTIONS = ["这和身高有关吗？", "这和录音有关吗？", "这与时间有关吗？", "这和年龄有关吗？"]

DEFAULTS = {"max_repeat_rate": 0.05, "max_irrelevant_rate": 0.5,
            "min_confirmed_coverage": 0.6, "max_calls_per_turn": 3.0}


class CountingModel:
    """记录模型调用次数，用来算每位队友回合的真实成本。"""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    @property
    def demo(self):
        return self.inner.demo

    def complete_json(self, system, payload, max_tokens=1200):
        self.calls += 1
        return self.inner.complete_json(system, payload, max_tokens)


def clusters(questions, threshold):
    """按相似度贪心聚类，用于把同一命题的不同措辞算作一次。"""
    from module2_teammate import similarity

    groups = []
    for question in questions:
        if not any(similarity(question, member) >= threshold for member in groups):
            groups.append(question)
    return groups


def play_game(client, model, rounds, teammate_count):
    state = client.post("/api/new", json={"source": "existing", "play_mode": "coop",
                                          "theme": "", "teammate_count": teammate_count}).json()
    if "error" in state:
        raise SystemExit("开局失败：%s" % state["error"])
    game = {"title": state["puzzle"]["title"], "fact_count": state["puzzle"]["fact_count"],
            "turns": [], "calls": [], "notice": "", "rounds": 0}
    for index in range(rounds):
        state = client.post("/api/question", json={"text": PLAYER_QUESTIONS[index % len(PLAYER_QUESTIONS)]}).json()
        if "error" in state:
            break
        game["rounds"] += 1
        while state.get("next_actor") == "teammate":
            before_calls, before_history = model.calls, len(state["history"])
            state = client.post("/api/teammate", json={}).json()
            if "error" in state:
                raise SystemExit("队友回合失败：%s" % state["error"])
            if len(state["history"]) == before_history:
                # 发言权交还玩家（线索耗尽或连续重复），本轮没有新回合。
                game["notice"] = state.get("notice", "")
                break
            game["turns"].append(state["history"][-1])
            game["calls"].append(model.calls - before_calls)
    return game


def summarize(games, threshold):
    turns = [turn for game in games for turn in game["turns"]]
    questions = [turn["question"] for turn in turns]
    verdicts = [turn.get("verdict", "") for turn in turns]
    calls = [count for game in games for count in game["calls"]]

    unique = clusters(questions, threshold) if questions else []
    repeat_rate = 1 - len(unique) / len(questions) if questions else 0.0
    irrelevant = sum(verdict == "无关" for verdict in verdicts)
    confirmed = sum(verdict == "正确" for verdict in verdicts)
    coverage = []
    for game in games:
        matched = sum(turn.get("verdict") == "正确" for turn in game["turns"])
        if game["fact_count"]:
            coverage.append(min(1.0, matched / game["fact_count"]))
    return {
        "games": len(games),
        "teammate_turns": len(turns),
        "unique_propositions": len(unique),
        "repeat_rate": round(repeat_rate, 3),
        "irrelevant_rate": round(irrelevant / len(verdicts), 3) if verdicts else 0.0,
        "confirmed_coverage": round(statistics.mean(coverage), 3) if coverage else 0.0,
        "calls_per_turn": round(statistics.mean(calls), 2) if calls else 0.0,
        "calls_p95": max(calls) if calls else 0,
        "verdicts": {label: verdicts.count(label) for label in ("正确", "错误", "无关") if label in verdicts},
    }


def check(metrics, limits):
    failures = []
    if metrics["repeat_rate"] > limits["max_repeat_rate"]:
        failures.append("重复率 %s > %s" % (metrics["repeat_rate"], limits["max_repeat_rate"]))
    if metrics["irrelevant_rate"] > limits["max_irrelevant_rate"]:
        failures.append("无关率 %s > %s" % (metrics["irrelevant_rate"], limits["max_irrelevant_rate"]))
    if metrics["confirmed_coverage"] < limits["min_confirmed_coverage"]:
        failures.append("确认覆盖 %s < %s" % (metrics["confirmed_coverage"], limits["min_confirmed_coverage"]))
    if metrics["calls_per_turn"] > limits["max_calls_per_turn"]:
        failures.append("每回合调用 %s > %s" % (metrics["calls_per_turn"], limits["max_calls_per_turn"]))
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="离线评测 AI 队友的提问质量与成本")
    parser.add_argument("--games", type=int, default=2, help="局数；演示题库两题会交替出现")
    parser.add_argument("--rounds", type=int, default=3, help="每局玩家提问轮数")
    parser.add_argument("--teammates", type=int, default=2, choices=(1, 2, 3))
    parser.add_argument("--live", action="store_true", help="调用真实模型（需要 API Key，会产生费用）")
    parser.add_argument("--json", action="store_true", help="只输出 JSON，便于 CI 解析")
    for name, value in DEFAULTS.items():
        parser.add_argument("--" + name.replace("_", "-"), type=float, default=value)
    args = parser.parse_args(argv)

    if not args.live:
        os.environ["DEMO_MODE"] = "true"

    from fastapi.testclient import TestClient

    from engine import AgentEngine
    from llm import ModelClient
    from module2_teammate import DUPLICATE_THRESHOLD
    from module3_host.api.app import create_app

    model = CountingModel(ModelClient())
    engine = AgentEngine(model)
    limits = {name: getattr(args, name) for name in DEFAULTS}

    with tempfile.TemporaryDirectory(prefix="teammate-eval-") as directory:
        with TestClient(create_app(Path(directory) / "eval.sqlite3", engine)) as client:
            state = client.get("/api/state").json()
            client.headers["X-CSRF-Token"] = state["csrf"]
            registered = client.post("/api/users/register", json={
                "email": "evaluation@example.com", "password": "evaluation-password", "display_name": "评测玩家"
            })
            if registered.status_code != 200:
                raise SystemExit("评测账号注册失败：%s" % registered.text)
            client.headers["X-CSRF-Token"] = registered.json()["csrf"]
            games = [play_game(client, model, args.rounds, args.teammates) for _ in range(args.games)]

    metrics = summarize(games, DUPLICATE_THRESHOLD)
    metrics["mode"] = "demo" if model.demo else "llm"
    metrics["limits"] = limits
    metrics["failures"] = check(metrics, limits)

    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print("模式：%s，%d 局 %d 轮" % (metrics["mode"], metrics["games"], args.rounds))
        print("队友回合 %d 次，唯一命题 %d 个" % (metrics["teammate_turns"], metrics["unique_propositions"]))
        print("重复率 %(repeat_rate)s | 无关率 %(irrelevant_rate)s | 确认覆盖 %(confirmed_coverage)s" % metrics)
        print("每回合模型调用 %(calls_per_turn)s（最高 %(calls_p95)s）" % metrics)
        print("判定分布：%s" % (metrics["verdicts"] or "无"))
        for game in games:
            print("  - %s：%d 回合%s" % (game["title"], len(game["turns"]),
                                        "；" + game["notice"] if game["notice"] else ""))
        print("阈值：%s" % metrics["limits"])
        if metrics["failures"]:
            for item in metrics["failures"]:
                print("未达标：" + item)
        else:
            print("全部指标达标")
    return 1 if metrics["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
