import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from llm import ModelClient, ModelError, load_env
from module1_puzzles.puzzles import DEMO_PUZZLES
from engine import AgentEngine
from module1_puzzles.retrieval import ApprovedPuzzleRetriever
from module3_host.storage import AuthError, Conflict, Repository
from .service import GameError, GameService, initial_game

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Answer = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class NewGame(Payload):
    source: Literal["existing", "new"] = "existing"
    play_mode: Literal["solo", "coop"] = "coop"
    teammate_count: int = Field(default=2, ge=1, le=3)
    theme: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""


class Question(Payload):
    text: Text


class FinalAnswer(Payload):
    text: Answer


class Profile(Payload):
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254,
                                          pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class Register(Profile):
    email: Email
    password: Password


class Login(Payload):
    email: Email
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class ChangePassword(Payload):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Password


class AdminUserUpdate(Payload):
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)] | None = None
    is_active: bool | None = None


def create_app(database_path=None, engine=None):
    load_env(Path.cwd() / ".env")

    @asynccontextmanager
    async def lifespan(app):
        repo = Repository(database_path or os.getenv("DATABASE_PATH", "data/puzzle-mate.sqlite3"))
        repo.seed(DEMO_PUZZLES)
        app.state.repository = repo
        app.state.service = GameService(repo, engine or AgentEngine(ModelClient(), retriever=ApprovedPuzzleRetriever(repo.puzzles)))
        yield

    app = FastAPI(title="问渊 API", version="0.2.0", lifespan=lifespan)

    @app.exception_handler(GameError)
    async def game_error(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=exc.status)

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=409)

    @app.exception_handler(AuthError)
    async def auth_error(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=exc.status)

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

    def set_session_cookie(response: Response, value):
        response.set_cookie("soup_session", value["id"], httponly=True, samesite="strict", max_age=86400,
                            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true")

    def session(request: Request, response: Response):
        value, fresh = request.app.state.repository.session(request.cookies.get("soup_session"))
        if fresh:
            set_session_cookie(response, value)
        if request.method not in ("GET", "HEAD") and not secrets.compare_digest(request.headers.get("X-CSRF-Token", "").encode(), value["csrf"].encode()):
            raise GameError("会话已过期，请刷新页面", 403)
        return value

    Session = Annotated[dict, Depends(session)]

    def require_user(request: Request, value, role=None):
        user = request.app.state.repository.user(value["user_id"])
        if not user or not user["email"]:
            raise AuthError("请先注册或登录", 401)
        if role and user["role"] != role:
            raise AuthError("无权执行此操作", 403)
        return user

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/state")
    def state(request: Request, session: Session):
        user = request.app.state.repository.user(session["user_id"])
        if not user["email"] or user["role"] != "player":
            return request.app.state.service.public(session, initial_game())
        return request.app.state.service.public(session)

    @app.get("/api/users/me")
    def me(request: Request, session: Session):
        return request.app.state.repository.user(session["user_id"])

    @app.patch("/api/users/me")
    def profile(data: Profile, request: Request, session: Session):
        require_user(request, session)
        return request.app.state.repository.rename(session["user_id"], data.display_name)

    @app.post("/api/users/register")
    def register(data: Register, request: Request, response: Response, session: Session):
        value, user = request.app.state.repository.register(session["id"], data.email, data.password, data.display_name)
        set_session_cookie(response, value)
        return {"user": user, "csrf": value["csrf"]}

    @app.post("/api/users/login")
    def login(data: Login, request: Request, response: Response, session: Session):
        value, user = request.app.state.repository.login(session["id"], data.email, data.password)
        set_session_cookie(response, value)
        return {"user": user, "csrf": value["csrf"]}

    @app.post("/api/users/logout")
    def logout(data: Payload, request: Request, response: Response, session: Session):
        value, user = request.app.state.repository.logout(session["id"])
        set_session_cookie(response, value)
        return {"user": user, "csrf": value["csrf"]}

    @app.post("/api/users/password")
    def password(data: ChangePassword, request: Request, session: Session):
        require_user(request, session)
        return request.app.state.repository.change_password(session["id"], data.current_password, data.new_password)

    @app.get("/api/admin/users")
    def admin_users(request: Request, session: Session,
                    q: Annotated[str, Query(max_length=100)] = "",
                    limit: Annotated[int, Query(ge=1, le=100)] = 50,
                    offset: Annotated[int, Query(ge=0)] = 0):
        require_user(request, session, "admin")
        return request.app.state.repository.admin_users(q, limit, offset)

    @app.patch("/api/admin/users/{uid}")
    def admin_update(uid: str, data: AdminUserUpdate, request: Request, session: Session):
        require_user(request, session, "admin")
        if data.display_name is None and data.is_active is None:
            raise AuthError("请提供要修改的字段", 422)
        return request.app.state.repository.admin_update_user(uid, data.display_name, data.is_active)

    @app.post("/api/new")
    def start(data: NewGame, request: Request, session: Session):
        require_user(request, session, "player")
        return request.app.state.service.start(session, data.source, data.play_mode, data.theme, data.teammate_count)

    @app.post("/api/question")
    def question(data: Question, request: Request, session: Session):
        require_user(request, session, "player")
        return request.app.state.service.act(session, "question", data.text)

    @app.post("/api/final")
    def final(data: FinalAnswer, request: Request, session: Session):
        require_user(request, session, "player")
        return request.app.state.service.act(session, "final", data.text)

    @app.post("/api/teammate")
    def teammate(request: Request, session: Session, data: Payload):
        require_user(request, session, "player")
        return request.app.state.service.act(session, "teammate")

    @app.post("/api/reveal")
    def reveal(request: Request, session: Session, data: Payload):
        require_user(request, session, "player")
        return request.app.state.service.act(session, "reveal")

    return app
