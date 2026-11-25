"""SQLite owns persistence; no imports from API or model modules."""
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .passwords import hash_password, verify_password


class Conflict(Exception):
    pass


class AuthError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS users(
 id TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL,
 expires_at REAL NOT NULL, current_game_id TEXT);
CREATE TABLE IF NOT EXISTS puzzles(
 id TEXT PRIMARY KEY, data TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS games(
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
 puzzle_id TEXT NOT NULL REFERENCES puzzles(id), state TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS messages(
 game_id TEXT NOT NULL REFERENCES games(id), position INTEGER NOT NULL,
 data TEXT NOT NULL, PRIMARY KEY(game_id, position));
CREATE TABLE IF NOT EXISTS teammate_memories(
 game_id TEXT PRIMARY KEY REFERENCES games(id), data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS games_session ON games(session_id);
"""


def encode(value):
    return json.dumps(value, ensure_ascii=False)


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
            if "email" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN email TEXT")
            if "password_hash" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            if "role" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'player'")
            if "is_active" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
            if "last_login_at" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN last_login_at REAL")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email ON users(email)")
            db.execute("DELETE FROM schema_version")
            db.execute("INSERT INTO schema_version VALUES(3)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def seed(self, puzzles):
        with self.connect() as db:
            db.executemany("INSERT OR IGNORE INTO puzzles VALUES(?,?,1)", [(p["id"], encode(p)) for p in puzzles])

    def session(self, sid=None):
        with self.connect() as db:
            row = db.execute("""SELECT s.* FROM sessions s JOIN users u ON u.id=s.user_id
                                WHERE s.id=? AND s.expires_at>? AND u.is_active=1""", (sid, time.time())).fetchone()
            if row:
                return dict(row), False
            sid, uid, csrf = secrets.token_urlsafe(32), str(uuid.uuid4()), secrets.token_urlsafe(24)
            db.execute("INSERT INTO users(id,display_name,created_at) VALUES(?,?,?)", (uid, "推理玩家", time.time()))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,NULL)", (sid, uid, csrf, time.time()+86400))
            return dict(db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()), True

    def user(self, uid):
        with self.connect() as db:
            row = db.execute("SELECT id,display_name,email,role,is_active FROM users WHERE id=?", (uid,)).fetchone()
            return dict(row) if row else None

    def rename(self, uid, name):
        with self.connect() as db:
            db.execute("UPDATE users SET display_name=? WHERE id=?", (name, uid))
        return self.user(uid)

    @staticmethod
    def _rotate_session(db, old_sid, uid, source_sid=None):
        new_sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        game_id = None
        if source_sid:
            source = db.execute("SELECT current_game_id FROM sessions WHERE id=?", (source_sid,)).fetchone()
            game_id = source[0] if source else None
        db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (new_sid, uid, csrf, time.time() + 86400, game_id))
        if game_id:
            db.execute("UPDATE games SET session_id=? WHERE id=? AND session_id=?", (new_sid, game_id, source_sid))
            db.execute("UPDATE sessions SET current_game_id=NULL WHERE id=?", (source_sid,))
        db.execute("UPDATE sessions SET expires_at=0 WHERE id=?", (old_sid,))
        return dict(db.execute("SELECT * FROM sessions WHERE id=?", (new_sid,)).fetchone())

    def register(self, sid, email, password, display_name):
        email = email.strip().lower()
        with self.connect() as db:
            current = db.execute("SELECT u.id,u.email FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.id=?", (sid,)).fetchone()
            if not current:
                raise AuthError("会话已过期，请刷新页面", 403)
            if current["email"]:
                raise AuthError("当前已登录，请先退出", 409)
            try:
                db.execute("UPDATE users SET email=?,password_hash=?,display_name=?,last_login_at=? WHERE id=?",
                           (email, hash_password(password), display_name, time.time(), current["id"]))
            except sqlite3.IntegrityError as exc:
                raise AuthError("该邮箱已注册", 409) from exc
            new_session = self._rotate_session(db, sid, current["id"], sid)
        return new_session, self.user(current["id"])

    def login(self, sid, email, password):
        email = email.strip().lower()
        with self.connect() as db:
            current = db.execute("""SELECT u.email FROM users u JOIN sessions s ON s.user_id=u.id
                                    WHERE s.id=? AND s.expires_at>?""", (sid, time.time())).fetchone()
            if not current:
                raise AuthError("会话已过期，请刷新页面", 403)
            if current["email"]:
                raise AuthError("当前已登录，请先退出", 409)
            account = db.execute("SELECT id,password_hash FROM users WHERE email=?", (email,)).fetchone()
            if not account or not verify_password(password, account["password_hash"]):
                raise AuthError("邮箱或密码错误", 401)
            active = db.execute("SELECT is_active FROM users WHERE id=?", (account["id"],)).fetchone()[0]
            if not active:
                raise AuthError("账号已被禁用，请联系管理员", 403)
            source = db.execute("""SELECT id FROM sessions WHERE user_id=? AND current_game_id IS NOT NULL
                                   ORDER BY expires_at DESC LIMIT 1""", (account["id"],)).fetchone()
            new_session = self._rotate_session(db, sid, account["id"], source["id"] if source else sid)
            db.execute("UPDATE users SET last_login_at=? WHERE id=?", (time.time(), account["id"]))
        return new_session, self.user(account["id"])

    def logout(self, sid):
        with self.connect() as db:
            uid = str(uuid.uuid4())
            db.execute("INSERT INTO users(id,display_name,created_at) VALUES(?,?,?)", (uid, "推理玩家", time.time()))
            new_session = self._rotate_session(db, sid, uid)
        return new_session, self.user(uid)

    def change_password(self, sid, current_password, new_password):
        with self.connect() as db:
            row = db.execute("""SELECT u.id,u.password_hash FROM users u JOIN sessions s ON s.user_id=u.id
                                WHERE s.id=? AND s.expires_at>?""", (sid, time.time())).fetchone()
            if not row or not row["password_hash"]:
                raise AuthError("请先登录", 401)
            if not verify_password(current_password, row["password_hash"]):
                raise AuthError("当前密码错误", 401)
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new_password), row["id"]))
            db.execute("UPDATE sessions SET expires_at=0 WHERE user_id=? AND id<>?", (row["id"], sid))
        return self.user(row["id"])

    def create_admin(self, email, password, display_name):
        email = email.strip().lower()
        with self.connect() as db:
            try:
                db.execute("""INSERT INTO users(id,display_name,created_at,email,password_hash,role)
                              VALUES(?,?,?,?,?,'admin')""",
                           (str(uuid.uuid4()), display_name, time.time(), email, hash_password(password)))
            except sqlite3.IntegrityError as exc:
                raise AuthError("该邮箱已存在", 409) from exc

    def admin_users(self, query="", limit=50, offset=0):
        pattern = f"%{query.strip()}%"
        with self.connect() as db:
            rows = db.execute("""SELECT u.id,u.email,u.display_name,u.created_at,u.last_login_at,u.is_active,
                                COUNT(g.id) AS game_count FROM users u
                                LEFT JOIN sessions s ON s.user_id=u.id
                                LEFT JOIN games g ON g.session_id=s.id
                                WHERE u.email IS NOT NULL AND u.role='player'
                                  AND (u.email LIKE ? OR u.display_name LIKE ?)
                                GROUP BY u.id ORDER BY u.created_at DESC LIMIT ? OFFSET ?""",
                              (pattern, pattern, limit, offset)).fetchall()
            total = db.execute("""SELECT COUNT(*) FROM users WHERE email IS NOT NULL AND role='player'
                                  AND (email LIKE ? OR display_name LIKE ?)""", (pattern, pattern)).fetchone()[0]
            return {"users": [dict(row) for row in rows], "total": total}

    def admin_update_user(self, uid, display_name=None, is_active=None):
        with self.connect() as db:
            row = db.execute("SELECT id FROM users WHERE id=? AND email IS NOT NULL AND role='player'", (uid,)).fetchone()
            if not row:
                raise AuthError("用户不存在", 404)
            if display_name is not None:
                db.execute("UPDATE users SET display_name=? WHERE id=?", (display_name, uid))
            if is_active is not None:
                db.execute("UPDATE users SET is_active=? WHERE id=?", (int(is_active), uid))
                if not is_active:
                    db.execute("UPDATE sessions SET expires_at=0 WHERE user_id=?", (uid,))
        return self.user(uid)

    def puzzles(self, demo=False):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM puzzles WHERE demo=1 OR ?=0", (int(demo),))]

    def load_game(self, sid):
        with self.connect() as db:
            row = db.execute("""SELECT g.* FROM games g JOIN sessions s ON s.current_game_id=g.id
                                WHERE s.id=? AND g.session_id=s.id""", (sid,)).fetchone()
            if row is None:
                return None
            state = json.loads(row["state"])
            state.update(id=row["id"], version=row["version"])
            state["puzzle"] = json.loads(db.execute("SELECT data FROM puzzles WHERE id=?", (row["puzzle_id"],)).fetchone()[0])
            state["history"] = [json.loads(item[0]) for item in db.execute("SELECT data FROM messages WHERE game_id=? ORDER BY position", (row["id"],))]
            return state

    @staticmethod
    def _state(game):
        return encode({k: v for k, v in game.items() if k not in ("puzzle", "history", "id", "version")})

    @staticmethod
    def _messages(db, game):
        db.execute("DELETE FROM messages WHERE game_id=?", (game["id"],))
        db.executemany("INSERT INTO messages VALUES(?,?,?)", [(game["id"], i, encode(m)) for i, m in enumerate(game["history"])])
        # Only publicly known question/verdict pairs enter teammate memory.
        memory = [{k: turn[k] for k in ("actor", "kind", "question", "verdict", "teammate_id", "teammate_name") if k in turn} for turn in game["history"] if turn["kind"] == "question"]
        db.execute("INSERT OR REPLACE INTO teammate_memories VALUES(?,?)", (game["id"], encode(memory)))

    def start_game(self, sid, game, expected_id):
        gid = str(uuid.uuid4())
        with self.connect() as db:
            # CAS prevents a slow generation from replacing a newer game.
            result = db.execute("UPDATE sessions SET current_game_id=? WHERE id=? AND current_game_id IS ?", (gid, sid, expected_id))
            if result.rowcount != 1:
                raise Conflict("当前局已变化，请刷新后重试")
            p = game["puzzle"]
            db.execute("INSERT OR IGNORE INTO puzzles VALUES(?,?,?)", (p["id"], encode(p), int("rules" in p)))
            db.execute("INSERT INTO games VALUES(?,?,?,?,0,?)", (gid, sid, p["id"], self._state(game), time.time()))
            self._messages(db, {**game, "id": gid})
        return {**game, "id": gid, "version": 0}

    def save_game(self, sid, game):
        with self.connect() as db:
            result = db.execute("""UPDATE games SET state=?,version=version+1 WHERE id=? AND session_id=? AND version=?
                                   AND id=(SELECT current_game_id FROM sessions WHERE id=?)""",
                                (self._state(game), game["id"], sid, game["version"], sid))
            if result.rowcount != 1:
                raise Conflict("当前局已被其他请求更新，请刷新后重试")
            self._messages(db, game)
        game["version"] += 1

    def memory(self, gid):
        with self.connect() as db:
            row = db.execute("SELECT data FROM teammate_memories WHERE game_id=?", (gid,)).fetchone()
            return json.loads(row[0]) if row else []
