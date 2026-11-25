import random

from contracts import Engine
from module2_teammate import DemoCluesExhausted
from module3_host.storage import Repository

MAX_TURNS = 200


class GameError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def initial_game():
    return dict(puzzle=None, history=[], status="idle", play_mode="coop", next_actor="player",
                pending_question=None, notice="", report=None, source="existing")


class GameService:
    def __init__(self, repository: Repository, engine: Engine):
        self.repository = repository
        self.engine = engine

    def public(self, session, game=None):
        game = game or self.repository.load_game(session["id"]) or initial_game()
        result = {k: game[k] for k in ("status", "history", "play_mode", "next_actor", "pending_question", "notice", "report", "source")}
        result.update(csrf=session["csrf"], mode="demo" if self.engine.demo else "llm", puzzle=None,
                      game_id=game.get("id"), turns=len(game["history"]), max_turns=MAX_TURNS)
        if game["puzzle"]:
            p = game["puzzle"]
            result["puzzle"] = dict(title=p["title"], surface=p["surface"], fact_count=len(p["key_points"]))
            if game["status"] in ("won", "scored", "revealed"):
                result["solution"] = dict(bottom=p["bottom"], key_points=p["key_points"])
        return result

    def start(self, session, source, play_mode, theme):
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
        game = self.repository.start_game(session["id"], game, current["id"] if current else None)
        return self.public(session, game)

    def act(self, session, action, text=""):
        game = self.repository.load_game(session["id"])
        if not game or game["status"] != "playing":
            raise GameError("请先开始新的一局", 409)
        if action == "reveal":
            game.update(status="revealed", pending_question=None, next_actor="player")
        else:
            if len(game["history"]) >= MAX_TURNS and action != "final":
                raise GameError("本局达到200次互动上限，请提交答案或揭晓", 409)
            actor = "teammate" if action == "teammate" else "player"
            if game["next_actor"] != actor or (actor == "teammate" and game["play_mode"] != "coop"):
                raise GameError("请等待当前回合完成", 409)
            if actor == "teammate":
                if game["pending_question"] is None:
                    try:
                        game["pending_question"] = self.engine.teammate(game["puzzle"]["surface"], self.repository.memory(game["id"]))
                    except DemoCluesExhausted as exc:
                        game.update(notice=str(exc), next_actor="player")
                        self.repository.save_game(session["id"], game)
                        return self.public(session, game)
                    # Persist before judging: retries and restarts reuse this question.
                    self.repository.save_game(session["id"], game)
                text = game["pending_question"]
            kind = "final" if action == "final" else "question"
            result = self.engine.score(game["puzzle"], text) if kind == "final" else self.engine.question(game["puzzle"], text)
            game["history"].append(dict(actor=actor, kind=kind, question=text, **result))
            game["pending_question"] = None
            game["next_actor"] = "teammate" if game["play_mode"] == "coop" and actor == "player" and kind == "question" and len(game["history"]) < MAX_TURNS else "player"
            if kind == "final":
                game.update(status="won" if result["verdict"] == "正确" else "scored", report=result["report"])
        self.repository.save_game(session["id"], game)
        return self.public(session, game)
