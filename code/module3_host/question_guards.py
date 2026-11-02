"""问句前置检查：不调用模型即可拦下开放式、多判断、索要答案和提示词注入。

这些规则只负责“把明显不适合三值判定的输入变成可解释的澄清提示”，
不负责判断真假；真正的语义判定仍交给汤主提示词。规则保持保守：
宁可让玩家改写一次，也不输出误导性的“是/不是”。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from .contracts import VERDICT_IRRELEVANT

FEEDBACK_INJECTION = "请围绕故事提出一个可以用“是”或“不是”回答的问题。"
FEEDBACK_ANSWER_REQUEST = "我不能直接说出汤底或关键事实。请提出一个具体的是非问题来验证你的猜想。"
FEEDBACK_OPEN_ENDED = "海龟汤只能回答“是 / 不是 / 无关”。请把问题改写成可以用“是”或“不是”回答的具体问题。"
FEEDBACK_MULTI_CLAIM = "这个问题包含多个可以分别判断的命题。请拆成一次只问一件事，我才能逐个回答。"


@dataclass(frozen=True)
class QuestionIssue:
    """命中前置规则时的澄清结果，verdict 固定为无关。"""

    code: str
    verdict: str
    feedback: str


# 只拦截带有明确“元指令”特征的注入，避免把故事里的“忽略规则”误判。
_INJECTION = re.compile(
    r"(?:忽略|无视|跳过|忘记|不要遵守|别管).{0,12}"
    r"(?:以上|之前|前面|所有|全部|系统|开发者|管理员|你的).{0,8}"
    r"(?:指令|规则|设定|提示|要求)"
    r"|(?:系统|开发者|管理员)(?:提示词|指令|消息|模式)"
    r"|(?:你现在|从现在起|接下来你).{0,8}(?:是|扮演|作为|进入|只回答)"
    r"|(?:输出|打印|重复|复述|泄露).{0,8}(?:系统提示|system\s*prompt|密钥|api\s*key|汤底|隐藏答案)"
    r"|jailbreak|prompt\s*injection|ignore\s+(?:all|previous|above)",
    re.IGNORECASE,
)

# 索要汤底/答案/关键事实/提示词，而不是故事角色之间的“告诉”。
_ANSWER_REQUEST = re.compile(
    r"(?:^|[，。！？；\s])"
    r"(?:请|帮我|麻烦|直接|快|立刻|马上|能不能|可以|那|那么|所以)?"
    r"(?:告诉我|说出|透露|泄露|公布|输出|打印|复述|重复)(?:一下)?"
    r"(?:汤底|真相|答案|关键事实|提示词|线索)"
    r"|(?:^|[，。！？；\s])(?:汤底|真相|答案|关键事实|提示词)(?:到底|究竟)?"
    r"(?:是什么|是多少|是什么样|有哪些|在哪)(?:[？?。！!]|$)"
    r"|(?:^|[，。！？；\s])(?:给我|发我|把).{0,8}(?:汤底|真相|答案|关键事实)"
    r"|(?:想知道|请问|问一下)(?:一下)?(?:汤底|真相|答案|关键事实|提示词)"
    r"(?:到底|究竟)?(?:是什么|是多少|有哪些)"
)

_WH_START = re.compile(
    r"^(?:请问|那么|所以|那)?\s*"
    r"(?:为什么|为何|怎么回事|怎么|怎样|如何|什么|啥|哪(?:个|些|里|儿)?|谁|"
    r"多少|几(?:个|条|次|岁|点|天|年|分钟|小时)?|多久|多大|多远|多高|多长|多深)"
)

_OPEN_ANYWHERE = re.compile(r"(?:为什么|为何|怎么|怎样|如何|怎么回事|发生什么|出什么事)")

# 明确的是非问形式。这里不把“么”当作语气词，避免把“什么”误判成是非问。
_YES_NO_FORM = re.compile(
    r"(?:是否|是不是|有没有|会不会|能不能|可不可以|对不对|行不行|好不好|要不要|该不该)"
    r"|吗\s*[?？]?\s*$"
)

_MULTI_CONJUNCTION = re.compile(r"(?:并且|而且|另外|此外|分别|以及)")
_ALTERNATIVE = re.compile(r"(?:是|因为|由于).{0,20}还是")
_BOTH_AND = re.compile(r"既.{0,15}又")
_TWO_SUBJECTS = re.compile(r"(?:和|与).{0,15}(?:都|分别)")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def _looks_open_ended(text: str) -> bool:
    if _YES_NO_FORM.search(text):
        return False
    if _OPEN_ANYWHERE.search(text):
        return True
    return bool(_WH_START.match(text))


def _looks_multi_claim(text: str) -> bool:
    if text.count("？") + text.count("?") > 1:
        return True
    if text.count("吗") > 1:
        return True
    if _MULTI_CONJUNCTION.search(text):
        return True
    if _ALTERNATIVE.search(text):
        return True
    if _BOTH_AND.search(text):
        return True
    return bool(_TWO_SUBJECTS.search(text))


def check_question(text: str) -> Optional[QuestionIssue]:
    """按优先级返回第一条澄清规则；没有命中时返回 None，继续语义判定。"""
    normalized = _normalize(text)
    if _INJECTION.search(normalized):
        return QuestionIssue("INJECTION", VERDICT_IRRELEVANT, FEEDBACK_INJECTION)
    if _ANSWER_REQUEST.search(normalized):
        return QuestionIssue("ANSWER_REQUEST", VERDICT_IRRELEVANT, FEEDBACK_ANSWER_REQUEST)
    if _looks_open_ended(normalized):
        return QuestionIssue("OPEN_ENDED", VERDICT_IRRELEVANT, FEEDBACK_OPEN_ENDED)
    if _looks_multi_claim(normalized):
        return QuestionIssue("MULTI_CLAIM", VERDICT_IRRELEVANT, FEEDBACK_MULTI_CLAIM)
    return None
