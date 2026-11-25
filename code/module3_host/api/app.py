import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints

from llm import ModelClient, ModelError, load_env
from module1_puzzles.puzzles import DEMO_PUZZLES
from engine import AgentEngine
from module3_host.storage import Conflict, Repository
from .service import GameError, GameService

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Answer = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class NewGame(Payload):
    source: Literal["existing", "new"] = "existing"
    play_mode: Literal["solo", "coop"] = "coop"
    theme: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""


class Question(Payload):
    text: Text


class FinalAnswer(Payload):
    text: Answer


class Profile(Payload):
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


def create_app(database_path=None, engine=None):
    load_env(Path.cwd() / ".env")

    @asynccontextmanager
    async def lifespan(app):
        repo = Repository(database_path or os.getenv("DATABASE_PATH", "data/puzzle-mate.sqlite3"))
        repo.seed(DEMO_PUZZLES)
        app.state.repository = repo
        app.state.service = GameService(repo, engine or AgentEngine(ModelClient()))
        yield

    app = FastAPI(title="问渊 API", version="0.2.0", lifespan=lifespan)

    @app.exception_handler(GameError)
    async def game_error(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=exc.status)

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=409)

    @app.exception_handler(ModelError)
    async def model_error(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=502)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"error": "请求字段、类型或长度不符合接口约定"}, status_code=422)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def session(request: Request, response: Response):
        value, fresh = request.app.state.repository.session(request.cookies.get("soup_session"))
        if fresh:
            response.set_cookie("soup_session", value["id"], httponly=True, samesite="strict", max_age=86400,
                                secure=os.getenv("COOKIE_SECURE", "false").lower() == "true")
        if request.method not in ("GET", "HEAD") and not secrets.compare_digest(request.headers.get("X-CSRF-Token", "").encode(), value["csrf"].encode()):
            raise GameError("会话已过期，请刷新页面", 403)
        return value

    Session = Annotated[dict, Depends(session)]

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/state")
    def state(request: Request, session: Session):
        return request.app.state.service.public(session)

    @app.get("/api/users/me")
    def me(request: Request, session: Session):
        return request.app.state.repository.user(session["user_id"])

    @app.patch("/api/users/me")
    def profile(data: Profile, request: Request, session: Session):
        return request.app.state.repository.rename(session["user_id"], data.display_name)

    @app.post("/api/new")
    def start(data: NewGame, request: Request, session: Session):
        return request.app.state.service.start(session, data.source, data.play_mode, data.theme)

    @app.post("/api/question")
    def question(data: Question, request: Request, session: Session):
        return request.app.state.service.act(session, "question", data.text)

    @app.post("/api/final")
    def final(data: FinalAnswer, request: Request, session: Session):
        return request.app.state.service.act(session, "final", data.text)

    @app.post("/api/teammate")
    def teammate(request: Request, session: Session, data: Payload):
        return request.app.state.service.act(session, "teammate")

    @app.post("/api/reveal")
    def reveal(request: Request, session: Session, data: Payload):
        return request.app.state.service.act(session, "reveal")

    return app
