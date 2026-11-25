"""Four-role generation with author-owned story graph and bounded revision."""
import uuid
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from llm import ModelError
from contracts import JsonModel
from .prompts import PLANNER_PROMPT, AUTHOR_PROMPT, REVIEW_PROMPT, REVISER_PROMPT
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


class PuzzleWorkflow:
    def __init__(self, model: JsonModel, max_revisions: int = 2, retriever=None):
        if not 0 <= max_revisions <= 3:
            raise ValueError("max_revisions must be between 0 and 3")
        self.model = model
        self.demo = model.demo
        self.max_revisions = max_revisions
        self.retriever = retriever or ApprovedPuzzleRetriever()
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
        return {"references": self.retriever.search(state["theme"]), "trace": ["retrieval"]}

    def _plan(self, state):
        plan = self.model.complete_json(PLANNER_PROMPT, {"theme": state["theme"], "references": state["references"]}, max_tokens=1000)
        return {"plan": plan, "trace": state["trace"] + ["planner"]}

    def _draft(self, state, revision=False):
        payload = {key: state[key] for key in ("theme", "plan", "references")}
        if revision:
            payload.update(previous=state["candidate"], review=state["feedback"])
        candidate = self.model.complete_json(REVISER_PROMPT if revision else AUTHOR_PROMPT, payload, max_tokens=4000)
        # Candidate structure and story quality are assessed together by the reviewer.
        return {"candidate": candidate, "attempts": state["attempts"] + 1,
                "trace": state["trace"] + ["revision" if revision else "author"]}

    def _author(self, state):
        return self._draft(state)

    def _revise(self, state):
        return self._draft(state, revision=True)

    def _review(self, state):
        result = self.model.complete_json(REVIEW_PROMPT,
            {key: state[key] for key in ("theme", "plan", "references", "candidate")}, max_tokens=1600)
        if (set(result) != {"approved", "feedback"} or type(result["approved"]) is not bool
                or not isinstance(result["feedback"], str) or len(result["feedback"]) > 2000
                or (not result["approved"] and not result["feedback"].strip())):
            raise ModelError("审核结果无效，题目未入库")
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
        state = self.graph.invoke({"theme": theme, "attempts": 0, "trace": [], "reviews": []})
        try:
            puzzle = state["candidate"]["puzzle"]
            return {"id": "generated-" + uuid.uuid4().hex,
                    **{key: puzzle[key] for key in ("title", "surface", "bottom", "key_points")},
                    "generation": {"approved": True, "attempts": state["attempts"], "trace": state["trace"],
                        "plan": state["plan"], "story_graph": state["candidate"]["story_graph"],
                        "reference_ids": [p["id"] for p in state["references"]],
                        "reviews": state["reviews"], "tags": [theme]}}
        except (KeyError, TypeError) as exc:
            raise ModelError("审核通过的结果无法装配为题目，本次未入库") from exc
