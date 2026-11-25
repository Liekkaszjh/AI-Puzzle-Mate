"""Composition of the three independent game modules; no HTTP or SQL here."""
from contracts import JsonModel
from module1_puzzles.workflow import PuzzleWorkflow
from module2_teammate import propose_question
from module3_host.host import judge


class AgentEngine:
    def __init__(self, model: JsonModel, max_revisions: int = 2, retriever=None):
        self.model = model
        self.demo = model.demo
        self.workflow = PuzzleWorkflow(model, max_revisions, retriever)

    def generate(self, theme):
        return self.workflow.generate(theme)

    def question(self, puzzle, text):
        return judge(self.model, puzzle, text)

    def score(self, puzzle, text):
        return judge(self.model, puzzle, text, "final")

    def teammate(self, surface, memory, teammate=None):
        # Teammates only receive publicly observable information.
        return propose_question(self.model, surface, memory, teammate)
