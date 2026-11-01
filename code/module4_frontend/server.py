import json
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from llm import ModelError
from module1_puzzles import choose_existing, generate_puzzle, save_generated
from module2_teammate import DemoCluesExhausted, propose_question
from module3_host import judge


ASSETS = Path(__file__).parent
MAX_TURNS = 200


class GameError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Session:
    def __init__(self):
        self.csrf = secrets.token_urlsafe(24)
        self.puzzle = None
        self.history = []
        self.status = "idle"
        self.play_mode = "coop"
        self.next_actor = "player"
        self.pending_question = None
        self.notice = ""
        self.report = None
        self.source = "existing"
        self.touched = time.time()
        self.lock = threading.Lock()

    def public(self, client):
        result = {
            "csrf": self.csrf, "mode": "demo" if client.demo else "llm",
            "status": self.status, "history": list(self.history),
            "turns": len(self.history), "max_turns": MAX_TURNS,
            "puzzle": None,
            "play_mode": self.play_mode, "next_actor": self.next_actor,
            "pending_question": self.pending_question, "notice": self.notice,
            "report": self.report, "source": self.source,
        }
        if self.puzzle:
            result["puzzle"] = {"title": self.puzzle["title"], "surface": self.puzzle["surface"], "fact_count": len(self.puzzle["key_points"])}
            if self.status in ("won", "scored", "revealed"):
                result["solution"] = {"bottom": self.puzzle["bottom"], "key_points": self.puzzle["key_points"]}
        return result


class GameServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, client):
        self.client = client
        self.sessions = {}
        self.sessions_lock = threading.Lock()
        super().__init__(address, Handler)

    def get_session(self, cookie_header):
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header or "")
        except Exception:
            pass
        sid = cookie["soup_session"].value if "soup_session" in cookie else None
        now = time.time()
        with self.sessions_lock:
            if sid in self.sessions and now - self.sessions[sid].touched < 86400:
                session = self.sessions[sid]
                session.touched = now
                return sid, session, False
            expired = [key for key, value in self.sessions.items() if now - value.touched > 86400 and not value.lock.locked()]
            for key in expired:
                del self.sessions[key]
            if len(self.sessions) >= 1000:
                raise GameError("本机游戏会话过多，请重启服务", 503)
            sid = secrets.token_urlsafe(32)
            session = Session()
            self.sessions[sid] = session
            return sid, session, True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 不记录用户的问题、故事真相或 API Key。
        pass

    def send_content(self, status, body, content_type="application/json; charset=utf-8", cookie=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header("Set-Cookie", "soup_session=" + cookie + "; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, status, data, cookie=None):
        self.send_content(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), cookie=cookie)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/state":
            try:
                sid, session, fresh = self.server.get_session(self.headers.get("Cookie"))
                if not session.lock.acquire(blocking=False):
                    raise GameError("当前操作尚未完成，请稍后再试", 409)
                try:
                    self.send_json(200, session.public(self.server.client), sid if fresh else None)
                finally:
                    session.lock.release()
            except GameError as exc:
                self.send_json(exc.status, {"error": str(exc)})
            return
        assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/styles.css": ("styles.css", "text/css; charset=utf-8")}
        for name in ("host", "player", "teammate"):
            assets["/" + name + ".svg"] = (name + ".svg", "image/svg+xml")
        if path in assets:
            filename, mime = assets[path]
            self.send_content(200, (ASSETS / filename).read_bytes(), mime)
        else:
            self.send_json(404, {"error": "页面不存在"})

    def do_POST(self):
        try:
            path = urlsplit(self.path).path
            if path not in ("/api/new", "/api/question", "/api/teammate", "/api/final", "/api/reveal"):
                raise GameError("接口不存在", 404)
            sid, session, _ = self.server.get_session(self.headers.get("Cookie"))
            if not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), session.csrf):
                raise GameError("会话已过期，请刷新页面后重试", 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise GameError("请求长度无效")
            if not 0 < length <= 12000:
                raise GameError("请求内容过长或为空", 413)
            try:
                data = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                raise GameError("请求必须是 JSON 对象")
            if not isinstance(data, dict):
                raise GameError("请求必须是 JSON 对象")
            if not session.lock.acquire(blocking=False):
                raise GameError("汤主正在处理上一条请求，请稍后再试", 409)
            try:
                self.dispatch(path, data, session)
                self.send_json(200, session.public(self.server.client))
            finally:
                session.lock.release()
        except GameError as exc:
            self.send_json(exc.status, {"error": str(exc)})
        except ModelError as exc:
            self.send_json(502, {"error": str(exc)})
        except Exception:
            self.send_json(500, {"error": "服务发生异常，请重试；必要时重启服务。"})

    @staticmethod
    def text_field(data, key, limit, optional=False):
        text = data.get(key, "")
        if not isinstance(text, str) or len(text.strip()) > limit or (not optional and not text.strip()):
            raise GameError("%s 需要填写 1 到 %d 字" % ("题材" if key == "theme" else "内容", limit))
        return text.strip()

    def dispatch(self, path, data, session):
        client = self.server.client
        if path == "/api/new":
            theme = self.text_field(data, "theme", 100, optional=True)
            play_mode = data.get("play_mode", "coop")
            if play_mode not in ("solo", "coop"):
                raise GameError("请选择单人模式或 AI 合作模式")
            previous_id = session.puzzle.get("id") if session.puzzle else None
            source = data.get("source", "existing")
            if source not in ("existing", "new"):
                raise GameError("题目来源必须是 existing 或 new")
            if source == "new":
                if client.demo:
                    raise GameError("生成新题需要配置 DeepSeek API Key；目前可以随机游玩已有题目")
                if not theme:
                    raise GameError("请先输入新题的主题")
                puzzle = generate_puzzle(client, theme, previous_id)
                save_generated(puzzle)
            else:
                puzzle = choose_existing(client, previous_id)
            # 生成成功后才替换，模型失败时仍保留旧的一局。
            session.puzzle = puzzle
            session.history = []
            session.status = "playing"
            session.play_mode = play_mode
            session.next_actor = "player"
            session.pending_question = None
            session.notice = ""
            session.source = source
            session.report = None
            return
        if not session.puzzle or session.status != "playing":
            raise GameError("请先开始新的一局；已结束的游戏不能继续提问", 409)
        if path == "/api/reveal":
            session.status = "revealed"
            session.pending_question = None
            session.next_actor = "player"
            return
        if len(session.history) >= MAX_TURNS and path != "/api/final":
            raise GameError("本局已达到 200 次互动上限，请揭晓汤底或开始新的一局", 409)
        if path == "/api/teammate":
            if session.play_mode != "coop" or session.next_actor != "teammate":
                raise GameError("当前不是 AI 队友的回合", 409)
            public_history = [{key: turn[key] for key in ("actor", "kind", "question", "verdict")} for turn in session.history]
            if session.pending_question is None:
                try:
                    session.pending_question = propose_question(client, session.puzzle["surface"], public_history)
                except DemoCluesExhausted as exc:
                    session.notice = str(exc)
                    session.next_actor = "player"
                    return
            question = session.pending_question
            kind, actor = "question", "teammate"
        else:
            if session.next_actor != "player":
                raise GameError("请等 AI 队友完成本轮提问后再发言", 409)
            question = self.text_field(data, "text", 1500 if path == "/api/final" else 300)
            kind = "final" if path == "/api/final" else "question"
            actor = "player"
        result = judge(client, session.puzzle, question, kind)
        # 判题成功后才写入记录。队友判题失败时保留问题，重试不会重新生成。
        session.history.append({"actor": actor, "kind": kind, "question": question, **result})
        session.pending_question = None
        session.next_actor = "teammate" if session.play_mode == "coop" and actor == "player" and kind == "question" and len(session.history) < MAX_TURNS else "player"
        if kind == "final" and result["verdict"] == "正确":
            session.status = "won"
        elif kind == "final":
            session.status = "scored"
        if kind == "final":
            session.report = result["report"]


def create_server(client, host="127.0.0.1", port=8000):
    return GameServer((host, port), client)
