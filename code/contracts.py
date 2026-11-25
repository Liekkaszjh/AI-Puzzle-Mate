"""Stable engine ports; API and storage implementations stay outside this package."""
from typing import Protocol


class JsonModel(Protocol):
    demo: bool

    def complete_json(self, system: str, payload: dict, max_tokens: int = 1200) -> dict: ...


class Engine(Protocol):
    demo: bool

    def generate(self, theme: str) -> dict: ...
    def question(self, puzzle: dict, text: str) -> dict: ...
    def score(self, puzzle: dict, text: str) -> dict: ...
    def teammate(self, surface: str, memory: list[dict], teammate: dict | None = None) -> str: ...
