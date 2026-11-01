"""模块共享的数据约定、参数校验与受控错误。"""

import json
from typing import Protocol, TypedDict


class PuzzleError(Exception):
    """仅使用本地错误文案，避免回显密钥或上游响应。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GenerationRequest(TypedDict):
    theme: str
    difficulty: str


class Message(TypedDict):
    role: str
    content: str


class ModelGateway(Protocol):
    """生成和审核都只依赖这个同步接口。"""

    def complete(self, messages: list[Message]) -> str: ...


DIFFICULTIES = ("简单", "普通", "困难")


def normalize_request(request: object) -> GenerationRequest:
    if not isinstance(request, dict):
        raise PuzzleError("INVALID_REQUEST", "请提供主题和难度。")
    theme = request.get("theme")
    difficulty = request.get("difficulty", "普通")
    if not isinstance(theme, str) or not 1 <= len(theme.strip()) <= 50:
        raise PuzzleError("INVALID_REQUEST", "主题须为1至50个字符。")
    if not isinstance(difficulty, str) or difficulty not in DIFFICULTIES:
        raise PuzzleError("INVALID_REQUEST", "难度须为简单、普通或困难。")
    return {"theme": theme.strip(), "difficulty": difficulty}


def _reject_constant(value: str) -> None:
    raise ValueError("不接受非JSON数值")


def parse_model_object(text: str) -> dict:
    """严格读取JSON对象，不补全残缺输出，不接受NaN等非JSON值。"""
    try:
        value = json.loads(text, parse_constant=_reject_constant)
        if not isinstance(value, dict):
            raise ValueError("需要对象")
        return value
    except (ValueError, TypeError):
        raise PuzzleError("MODEL_OUTPUT_INVALID", "模型未返回合法的 JSON 对象。") from None
