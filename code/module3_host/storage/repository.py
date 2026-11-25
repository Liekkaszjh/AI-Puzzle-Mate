"""SQLite owns persistence; no imports from API or model modules."""
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class Conflict(Exception):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES(1);
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
            row = db.execute("SELECT * FROM sessions WHERE id=? AND expires_at>?", (sid, time.time())).fetchone()
            if row:
                return dict(row), False
            sid, uid, csrf = secrets.token_urlsafe(32), str(uuid.uuid4()), secrets.token_urlsafe(24)
            db.execute("INSERT INTO users VALUES(?,?,?)", (uid, "推理玩家", time.time()))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,NULL)", (sid, uid, csrf, time.time()+86400))
            return dict(db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()), True

    def user(self, uid):
        with self.connect() as db:
            return dict(db.execute("SELECT id,display_name FROM users WHERE id=?", (uid,)).fetchone())

    def rename(self, uid, name):
        with self.connect() as db:
            db.execute("UPDATE users SET display_name=? WHERE id=?", (name, uid))
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
