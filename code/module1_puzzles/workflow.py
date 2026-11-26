"""Four-role generation with author-owned story graph and bounded revision."""
import uuid
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from llm import ModelError
from contracts import JsonModel
from .agents import PlannerAgent, AuthorAgent, ReviewerAgent, ReviserAgent
from .guardrails import GuardrailError, validate_theme, validate_references, validate_candidate
from .retrieval import ApprovedPuzzleRetriever


class GenerationState(TypedDict, total=False):
    theme: str
    references: list[dict]
    plan: dict
    candidate: dict
    feedback: str
    approved: bool
    attempts: int
    trace: list[str]
    reviews: list[dict]
    guardrail_error: str


class PuzzleWorkflow:
    def __init__(self, model: JsonModel, max_revisions: int = 2, retriever=None):
        if not 0 <= max_revisions <= 3:
            raise ValueError("max_revisions must be between 0 and 3")
        self.model = model
        self.demo = model.demo
        self.max_revisions = max_revisions
        self.retriever = retriever or ApprovedPuzzleRetriever()
        self.planner = PlannerAgent(model)
        self.author = AuthorAgent(model)
        self.reviewer = ReviewerAgent(model)
        self.reviser = ReviserAgent(model)
        builder = StateGraph(GenerationState)
        for name, action in (("retrieval", self._retrieve), ("planner", self._plan),
                             ("author", self._author), ("reviewer", self._review),
                             ("revision", self._revise), ("reject", self._reject)):
            builder.add_node(name, action)
        builder.add_edge(START, "retrieval")
        builder.add_edge("retrieval", "planner")
        builder.add_edge("planner", "author")
        builder.add_edge("author", "reviewer")
        builder.add_conditional_edges("reviewer", self._route,
                                     {"done": END, "revise": "revision", "reject": "reject"})
        builder.add_edge("revision", "reviewer")
        builder.add_edge("reject", END)
        self.graph = builder.compile()

    def _retrieve(self, state):
        return {"references": validate_references(self.retriever.search(state["theme"])), "trace": ["retrieval"]}

    def _plan(self, state):
        plan = self.planner.run(state["theme"], state["references"])
        return {"plan": plan, "trace": state["trace"] + ["planner"]}

    def _draft(self, state, revision=False):
        if revision:
            candidate = self.reviser.run(state["theme"], state["plan"], state["references"],
                                         state["candidate"], state["feedback"])
        else:
            candidate = self.author.run(state["theme"], state["plan"], state["references"])
        error = ""
        try:
            candidate = validate_candidate(candidate)
        except GuardrailError as exc:
            error = str(exc)
        return {"candidate": candidate, "guardrail_error": error, "attempts": state["attempts"] + 1,
                "trace": state["trace"] + ["revision" if revision else "author"]}

    def _author(self, state):
        return self._draft(state)

    def _revise(self, state):
        return self._draft(state, revision=True)

    def _review(self, state):
        # Bad structures are never sent to the semantic reviewer or accepted by its approval.
        if state.get("guardrail_error"):
            result = {"approved": False, "feedback": state["guardrail_error"]}
        else:
            result = self.reviewer.run(state["theme"], state["plan"], state["references"], state["candidate"])
        return {**result, "reviews": state["reviews"] + [result], "trace": state["trace"] + ["reviewer"]}

    def _route(self, state):
        if state["approved"]:
            return "done"
        return "revise" if state["attempts"] <= self.max_revisions else "reject"

    def _reject(self, state):
        raise ModelError("题目经限定次数修改后仍未通过审核，请更换主题后重试")

    def generate(self, theme):
        if self.demo:
            raise ModelError("新题生成需要配置 DeepSeek，并关闭 DEMO_MODE")
        theme = validate_theme(theme)
        state = self.graph.invoke({"theme": theme, "attempts": 0, "trace": [], "reviews": []})
        try:
            candidate = validate_candidate(state["candidate"])
            puzzle = candidate["puzzle"]
            return {"id": "generated-" + uuid.uuid4().hex,
                    **{key: puzzle[key] for key in ("title", "surface", "bottom", "key_points")},
                    "generation": {"approved": True, "attempts": state["attempts"], "trace": state["trace"],
                        "plan": state["plan"], "story_graph": candidate["story_graph"],
                        "reference_ids": [p["id"] for p in state["references"]],
                        "reviews": state["reviews"], "tags": [theme]}}
        except (KeyError, TypeError) as exc:
            raise ModelError("审核通过的结果无法装配为题目，本次未入库") from exc
