import random
from copy import deepcopy

from contracts import Engine
from module2_teammate import TEAMMATES, TeammateYield
from module2_teammate.board import hint, new_board, record_turn, restore_board, view
from module3_host.storage import Repository

MAX_TURNS = 200


class GameError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def teammate_turn(proposal):
    """接受结构化回合；纯字符串是旧引擎的返回值，仍按无 target 处理。"""
    if isinstance(proposal, str) and proposal.strip():
        return proposal.strip(), "", ""
    if isinstance(proposal, dict):
        question = proposal.get("question")
        if isinstance(question, str) and question.strip():
            target = proposal.get("target")
            rationale = proposal.get("rationale")
            return (question.strip(), target if isinstance(target, str) else "",
                    rationale if isinstance(rationale, str) else "")
    raise GameError("队友没有返回可用的提问", 502)


def initial_game():
    return dict(puzzle=None, history=[], status="idle", play_mode="coop", next_actor="player",
                pending_question=None, pending_target="", pending_rationale="", notice="", report=None,
                source="existing", teammates=[], teammate_index=0, board=new_board())


def restore_team(game):
    # Existing one-teammate games keep their original round order.
    game.setdefault("teammates", deepcopy(TEAMMATES[:1]) if game["play_mode"] == "coop" else [])
    game.setdefault("teammate_index", 0)
    game.setdefault("pending_target", "")
    game.setdefault("pending_rationale", "")
    # 老存档没有黑板：按公开历史之外的空白板恢复，不迁移数据库结构。
    game["board"] = restore_board(game.get("board"))
    return game


class GameService:
    def __init__(self, repository: Repository, engine: Engine):
        self.repository = repository
        self.engine = engine

    def public(self, session, game=None):
        game = game or self.repository.load_game(session["id"]) or initial_game()
        restore_team(game)
        result = {k: game[k] for k in ("status", "history", "play_mode", "next_actor", "pending_question", "notice", "report", "source")}
        result.update(csrf=session["csrf"], mode="demo" if self.engine.demo else "llm", puzzle=None,
                      game_id=game.get("id"), turns=len(game["history"]), max_turns=MAX_TURNS)
        result["teammates"] = game["teammates"]
        result["next_teammate"] = game["teammates"][game["teammate_index"]] if game["next_actor"] == "teammate" and game["teammates"] else None
        result["board"] = view(game["board"])
        result["hint"] = ""
        if game["puzzle"]:
            p = game["puzzle"]
            result["puzzle"] = dict(title=p["title"], surface=p["surface"], fact_count=len(p["key_points"]))
            if game["status"] == "playing":
                result["hint"] = hint(game["board"], len(p["key_points"]))
            if game["status"] in ("won", "scored", "revealed"):
                result["solution"] = dict(bottom=p["bottom"], key_points=p["key_points"])
        return result

    def start(self, session, source, play_mode, theme, teammate_count=2):
        current = self.repository.load_game(session["id"])
        if source == "new":
            if self.engine.demo or not theme:
                raise GameError("生成新题需要填写主题、配置 DeepSeek 并关闭演示模式")
            puzzle = self.engine.generate(theme)
        else:
            library = self.repository.puzzles(self.engine.demo)
            previous_id = current["puzzle"]["id"] if current else None
            puzzle = random.choice([p for p in library if p["id"] != previous_id] or library)
        game = initial_game()
        game.update(puzzle=puzzle, status="playing", source=source, play_mode=play_mode)
        game["teammates"] = deepcopy(TEAMMATES[:teammate_count]) if play_mode == "coop" else []
        game = self.repository.start_game(session["id"], game, current["id"] if current else None)
        return self.public(session, game)

    def act(self, session, action, text=""):
        game = self.repository.load_game(session["id"])
        if not game or game["status"] != "playing":
            raise GameError("请先开始新的一局", 409)
        restore_team(game)
        if action == "reveal":
            game.update(status="revealed", pending_question=None, next_actor="player", teammate_index=0)
        else:
            if len(game["history"]) >= MAX_TURNS and action != "final":
                raise GameError("本局达到200次互动上限，请提交答案或揭晓", 409)
            actor = "teammate" if action == "teammate" else "player"
            if game["next_actor"] != actor or (actor == "teammate" and game["play_mode"] != "coop"):
                raise GameError("请等待当前回合完成", 409)
            if actor == "teammate":
                teammate = game["teammates"][game["teammate_index"]]
                if game["pending_question"] is None:
                    try:
                        proposal = self.engine.teammate(game["puzzle"]["surface"], self.repository.memory(game["id"]),
                                                       teammate, game["board"])
                    except TeammateYield as exc:
                        game.update(notice=str(exc), next_actor="player", teammate_index=0)
                        self.repository.save_game(session["id"], game)
                        return self.public(session, game)
                    question, target, rationale = teammate_turn(proposal)
                    game.update(pending_question=question, pending_target=target, pending_rationale=rationale)
                    # Persist before judging: retries and restarts reuse this question.
                    self.repository.save_game(session["id"], game)
                text = game["pending_question"]
            kind = "final" if action == "final" else "question"
            result = self.engine.score(game["puzzle"], text) if kind == "final" else self.engine.question(game["puzzle"], text)
            turn = dict(actor=actor, kind=kind, question=text, **result)
            if actor == "teammate":
                turn.update(teammate_id=teammate["id"], teammate_name=teammate["name"],
                            target=game["pending_target"], rationale=game["pending_rationale"])
                record_turn(game["board"], turn)
            game["history"].append(turn)
            game.update(pending_question=None, pending_target="", pending_rationale="", next_actor="player")
            if kind == "question" and game["teammates"] and len(game["history"]) < MAX_TURNS:
                if actor == "player":
                    game["teammate_index"] = 0
                    game["next_actor"] = "teammate"
                elif game["teammate_index"] + 1 < len(game["teammates"]):
                    game["teammate_index"] += 1
                    game["next_actor"] = "teammate"
            if game["next_actor"] == "player":
                game["teammate_index"] = 0
            if kind == "final":
                game.update(status="won" if result["verdict"] == "正确" else "scored", report=result["report"])
        self.repository.save_game(session["id"], game)
        return self.public(session, game)
