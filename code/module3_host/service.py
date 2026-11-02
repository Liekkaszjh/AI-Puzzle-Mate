"""汤主服务：把前置规则、历史一致性、模型判定和泄底防护串成一次调用。

设计约束：
- 每次问句判定最多一次模型请求，不做自动网络重试或隐藏的第二轮调用；
- 相同问题直接复用公开历史中的既有判定，保证回答一致并节省调用；
- 模型返回的 feedback 一律丢弃，只使用本地生成的澄清/评分文案，避免泄底。
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, List, Mapping, Optional, Tuple

from llm import ModelError

from .contracts import (
    FINAL_CORRECT,
    FINAL_PARTIAL,
    MAX_ANSWER_LENGTH,
    MAX_QUESTION_LENGTH,
    HostAnswer,
    canonical_question_verdict,
    normalize_puzzle,
    normalize_text,
    verdict_code,
)
from .demo import judge_demo
from .history import MAX_HISTORY_TURNS, find_prior, public_history
from .leak_guard import sanitize_feedback
from .prompts import QUESTION_PROMPT
from .question_guards import check_question
from .scoring import score_reconstruction


class HostService:
    """无状态汤主；同一个实例可被多个会话并发调用。"""

    def __init__(self, client: Any) -> None:
        if client is None or not callable(getattr(client, "complete_json", None)):
            raise TypeError("汤主需要提供 complete_json 的模型客户端")
        self.client = client

    def ask(
        self,
        puzzle: dict,
        text: str,
        history: Optional[List[Mapping[str, Any]]] = None,
        *,
        recheck: bool = False,
    ) -> HostAnswer:
        """判定一个问句，返回 是/不是/无关。

        默认复用签名相同的历史判定；recheck=True 时强制调用模型，
        用于按汤底复核历史记录，必要时纠正旧回答。
        """
        started = perf_counter()
        normalized_puzzle = normalize_puzzle(puzzle)
        question = normalize_text(text, MAX_QUESTION_LENGTH, "问题")
        history_items = list(history or [])
        history_size = len(public_history(history_items, limit=0))

        issue = check_question(question)
        if issue is not None:
            return _build_answer(
                issue.verdict, issue.feedback, "guard", started, history_size,
            )

        prior = find_prior(history_items, question)
        if prior is not None and not recheck:
            return _build_answer(
                prior["verdict"], "", "history", started, history_size,
            )

        if getattr(self.client, "demo", False):
            verdict, feedback = judge_demo(normalized_puzzle, question)
            source = "demo"
        else:
            payload = {
                "bottom": normalized_puzzle["bottom"],
                "key_points": normalized_puzzle["key_points"],
                "kind": "question",
                "history": public_history(history_items, limit=MAX_HISTORY_TURNS),
                "text": question,
            }
            data = self.client.complete_json(QUESTION_PROMPT, payload, max_tokens=512)
            verdict, _model_feedback = _read_model_verdict(data)
            # 模型反馈可能以改写方式泄底；公开文案只使用本地规则生成的澄清语。
            feedback = ""
            source = "model"

        if prior is not None and recheck and verdict != prior["verdict"]:
            source = "model_corrected"
            feedback = "此前记录与汤底不一致，已按汤底更正。"
        feedback = sanitize_feedback(feedback, normalized_puzzle, fallback="")
        return _build_answer(verdict, feedback, source, started, history_size)

    def submit(
        self,
        puzzle: dict,
        text: str,
        history: Optional[List[Mapping[str, Any]]] = None,
    ) -> HostAnswer:
        """评分并给出 正确/部分正确/错误；不提前公开未命中的事实。"""
        started = perf_counter()
        normalized_puzzle = normalize_puzzle(puzzle)
        answer = normalize_text(text, MAX_ANSWER_LENGTH, "还原答案")
        report = score_reconstruction(self.client, normalized_puzzle, answer)
        verdict = report["outcome"]
        feedback = _final_feedback(report)
        feedback = sanitize_feedback(feedback, normalized_puzzle, fallback="得分 %s / 100。" % report["score"])
        return _build_answer(
            verdict,
            feedback,
            "scoring",
            started,
            len(public_history(list(history or []), limit=0)),
            report=report,
        )

    def score(self, puzzle: dict, text: str) -> Dict[str, Any]:
        """直接暴露逐条评分报告，供复盘或测试使用。"""
        return score_reconstruction(self.client, puzzle, text)


def _build_answer(
    verdict: str,
    feedback: str,
    source: str,
    started: float,
    history_size: int,
    *,
    report: Optional[Dict[str, Any]] = None,
) -> HostAnswer:
    return HostAnswer(
        verdict=verdict,
        feedback=feedback,
        source=source,
        canonical=verdict_code(verdict),
        history_size=history_size,
        report=report,
        timings_ms={"total_ms": int((perf_counter() - started) * 1000)},
    )


def _read_model_verdict(data: Any) -> Tuple[str, str]:
    """严格读取模型协议，拒绝多余字段和无法识别的判定。"""
    if not isinstance(data, dict):
        raise ModelError("汤主返回的不是 JSON 对象，请重试当前操作")
    if "verdict" not in data or not set(data) <= {"verdict", "feedback"}:
        raise ModelError("汤主返回字段必须且只能包含 verdict 和 feedback")
    feedback = data.get("feedback", "")
    if not isinstance(feedback, str):
        raise ModelError("汤主返回的 feedback 必须是字符串")

    verdict = canonical_question_verdict(data.get("verdict"))
    if verdict is None:
        raise ModelError("汤主返回的 verdict 不是“是”“不是”或“无关”，请重试当前操作")
    return verdict, feedback


def _final_feedback(report: Dict[str, Any]) -> str:
    outcome = report.get("outcome")
    matched = report.get("matched_count", 0)
    total = report.get("total_facts", 0)
    score = report.get("score", 0)
    if outcome == FINAL_CORRECT:
        return "全部 %d 条关键事实均已命中，得分 100。" % total
    if outcome == FINAL_PARTIAL:
        return "已命中 %d/%d 条关键事实，得分 %s；未命中的事实不会提前公开。" % (
            matched, total, score,
        )
    return "本次还原未命中关键事实，得分 %s；可以继续提问后再次提交。" % score


def judge_detailed(
    client: Any,
    puzzle: dict,
    text: str,
    kind: str = "question",
    history: Optional[List[Mapping[str, Any]]] = None,
    *,
    recheck: bool = False,
) -> HostAnswer:
    """返回带来源、耗时和评分报告的完整结果，供复盘或日志使用。"""
    if kind not in ("question", "final"):
        raise ValueError("kind 必须是 question 或 final")
    service = HostService(client)
    if kind == "final":
        return service.submit(puzzle, text, history)
    return service.ask(puzzle, text, history, recheck=recheck)


def judge(
    client: Any,
    puzzle: dict,
    text: str,
    kind: str = "question",
    history: Optional[List[Mapping[str, Any]]] = None,
    *,
    recheck: bool = False,
) -> Dict[str, Any]:
    """模块3的稳定入口，保持 judge(client, puzzle, text, kind, history) 调用方式。

    question: 返回 {"verdict": "是|不是|无关", "feedback": str}
    final:    返回 {"verdict": "正确|部分正确|错误", "feedback": str, "report": dict}
    recheck=True 时忽略重复问题复用，强制按汤底复核历史。
    """
    answer = judge_detailed(client, puzzle, text, kind, history, recheck=recheck)
    if kind == "final":
        return {"verdict": answer.verdict, "feedback": answer.feedback, "report": answer.report}
    return {"verdict": answer.verdict, "feedback": answer.feedback}


__all__ = ["HostService", "judge", "judge_detailed", "score_reconstruction"]
