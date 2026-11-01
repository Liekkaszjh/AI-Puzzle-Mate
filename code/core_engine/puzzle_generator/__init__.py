"""独立海龟汤题目生成模块，Python 3.11+，无第三方运行依赖。"""

from .checker import PuzzleChecker, check_structure
from .contracts import ModelGateway, PuzzleError
from .generator import PuzzleGenerator
from .model_client import ChatModelClient
from .service import PuzzleService

__all__ = [
    "ChatModelClient", "ModelGateway", "PuzzleChecker", "PuzzleError",
    "PuzzleGenerator", "PuzzleService", "check_structure",
]
