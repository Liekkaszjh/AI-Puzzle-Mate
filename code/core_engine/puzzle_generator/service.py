"""流程入口：参数校验、生成、审核、有限重试和阶段计时。"""

from time import perf_counter
from typing import Callable
from uuid import uuid4

from .checker import PuzzleChecker, select_puzzle_fields
from .contracts import ModelGateway, PuzzleError, normalize_request
from .generator import PuzzleGenerator


class PuzzleService:
    def __init__(
        self, model: ModelGateway, *, review_model: ModelGateway | None = None, max_retries: int = 3,
    ) -> None:
        review_model = model if review_model is None else review_model
        if not all(callable(getattr(item, "complete", None)) for item in (model, review_model)):
            raise TypeError("生成与审核模型均须实现complete(messages)。")
        if type(max_retries) is not int or not 0 <= max_retries <= 3:
            raise ValueError("max_retries须为0至3的整数。")
        self.generator = PuzzleGenerator(model)
        self.checker = PuzzleChecker(review_model)
        self.max_retries = max_retries

    def generate(self, request: object, *, on_progress: Callable[[dict], None] | None = None) -> dict:
        started = perf_counter()
        generation_seconds = review_seconds = 0.0
        attempts = 0

        def notify(stage: str, **details) -> None:
            if on_progress is not None:
                try:
                    on_progress({"stage": stage, "attempt": attempts, "max_attempts": self.max_retries + 1, **details})
                except Exception:
                    # 进度展示失败不影响生成结果；不把观察者异常混入业务错误。
                    pass

        def finish(result: dict) -> dict:
            result["timings"] = {
                "generation_ms": round(generation_seconds * 1000),
                "review_ms": round(review_seconds * 1000),
                "total_ms": round((perf_counter() - started) * 1000),
            }
            result["attempts"] = attempts
            return result

        try:
            normalized = normalize_request(request)
            issues: list[str] = []
            for _ in range(self.max_retries + 1):
                attempts += 1
                notify("generating")
                phase_started = perf_counter()
                try:
                    draft = self.generator.generate(normalized, issues)
                except PuzzleError as error:
                    if error.code != "MODEL_OUTPUT_INVALID":
                        raise
                    issues = [str(error)]
                    notify("rejected", issues=list(issues), will_retry=attempts <= self.max_retries)
                    continue
                finally:
                    generation_seconds += perf_counter() - phase_started
                phase_started = perf_counter()
                notify("checking")
                try:
                    review = self.checker.check(draft, normalized)
                finally:
                    review_seconds += perf_counter() - phase_started
                if review["passed"]:
                    notify("accepted")
                    return finish({
                        "success": True,
                        "puzzle": {"id": str(uuid4()), **select_puzzle_fields(draft)},
                        "review": review,
                    })
                issues = review["issues"]
                notify("rejected", issues=list(issues), will_retry=attempts <= self.max_retries)
            return finish({
                "success": False,
                "error": {
                    "code": "QUALITY_RETRY_EXHAUSTED",
                    "message": ("本次题目未通过检查（自动重新生成已关闭）。" if self.max_retries == 0
                                else "题目未通过检查，已达到重新生成上限。"),
                    "issues": issues,
                },
            })
        except PuzzleError as error:
            return finish({"success": False, "error": {"code": error.code, "message": str(error)}})
        except Exception:
            return finish({"success": False, "error": {"code": "INTERNAL_ERROR", "message": "题目生成发生内部错误。"}})
