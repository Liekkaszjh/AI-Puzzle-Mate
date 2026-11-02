"""模块3：汤主。依据汤底判断提问或最终还原。

问句判定只有三种结果：是 / 不是 / 无关；还原判定为：正确 / 部分正确 / 错误。
对外保持原有的 judge / score_reconstruction 调用签名：

    from module3_host import judge, score_reconstruction

    judge(client, puzzle, "他带伞了吗？", "question", history)
    score_reconstruction(client, puzzle, "完整还原……")
"""

from .contracts import (
    FINAL_CORRECT,
    FINAL_PARTIAL,
    FINAL_WRONG,
    MAX_ANSWER_LENGTH,
    MAX_FEEDBACK_LENGTH,
    MAX_QUESTION_LENGTH,
    QUESTION_VERDICTS,
    VERDICT_IRRELEVANT,
    VERDICT_NO,
    VERDICT_YES,
    HostAnswer,
    final_outcome,
)
from .scoring import score_reconstruction
from .service import HostService, judge, judge_detailed

__all__ = [
    "HostService",
    "HostAnswer",
    "judge",
    "judge_detailed",
    "score_reconstruction",
    "final_outcome",
    "VERDICT_YES",
    "VERDICT_NO",
    "VERDICT_IRRELEVANT",
    "QUESTION_VERDICTS",
    "FINAL_CORRECT",
    "FINAL_PARTIAL",
    "FINAL_WRONG",
    "MAX_QUESTION_LENGTH",
    "MAX_ANSWER_LENGTH",
    "MAX_FEEDBACK_LENGTH",
]
